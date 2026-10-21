from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, engine, get_db
from app.models import Bug, User
from app.schemas import BugCreate, BugOut, BugUpdate, Token, UserCreate, UserOut
from app.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


_docs = get_settings().enable_docs
app = FastAPI(
    title="Bugtracker",
    lifespan=lifespan,
    docs_url="/docs" if _docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _docs else None,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    if not request.url.path.startswith(("/docs", "/openapi.json")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
    return response


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "database": "unreachable"},
        )
    return {"status": "ok", "database": "ok"}


# --- Auth ---------------------------------------------------------------


@app.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    user = User(email=data.email.lower(), password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    return user


@app.post("/auth/login", response_model=Token)
def login(data: UserCreate, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not verify_password(data.password, user.password_hash if user else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return Token(access_token=create_access_token(user.id))


# --- Bugs (CRUD) ----------------------------------------------------------


def _get_bug(bug_id: int, db: Session) -> Bug:
    bug = db.get(Bug, bug_id)
    if bug is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bug not found")
    return bug


def _require_owner(bug: Bug, user: User) -> None:
    if bug.reporter_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the reporter can modify this bug")


@app.get("/bugs", response_model=list[BugOut])
def list_bugs(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    limit = max(1, min(limit, 100))
    stmt = select(Bug).order_by(Bug.id).limit(limit).offset(max(0, offset))
    return db.scalars(stmt).all()


@app.post("/bugs", response_model=BugOut, status_code=status.HTTP_201_CREATED)
def create_bug(
    data: BugCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bug = Bug(**data.model_dump(), reporter_id=user.id)
    db.add(bug)
    db.commit()
    db.refresh(bug)
    return bug


@app.get("/bugs/{bug_id}", response_model=BugOut)
def get_bug(
    bug_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return _get_bug(bug_id, db)


@app.patch("/bugs/{bug_id}", response_model=BugOut)
def update_bug(
    bug_id: int,
    data: BugUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bug = _get_bug(bug_id, db)
    _require_owner(bug, user)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(bug, field, value)
    db.commit()
    db.refresh(bug)
    return bug


@app.delete("/bugs/{bug_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bug(
    bug_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bug = _get_bug(bug_id, db)
    _require_owner(bug, user)
    db.delete(bug)
    db.commit()
