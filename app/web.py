"""Server-rendered web UI (Jinja2, autoescaping on).

Session: JWT in an HttpOnly, SameSite=Strict cookie.
CSRF: double-submit token (cookie + hidden form field) on every POST.
"""

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import bugs
from app.config import get_settings
from app.db import get_db
from app.models import Bug, BugPriority, BugStatus, User
from app.schemas import BugCreate, BugUpdate, UserCreate
from app.security import (
    create_access_token,
    hash_password,
    user_from_token,
    verify_password,
)

SESSION_COOKIE = "session"
CSRF_COOKIE = "csrf_token"

router = APIRouter(prefix="/ui", include_in_schema=False)
templates = Jinja2Templates(
    env=Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=True
    )
)


# --- helpers -------------------------------------------------------------


def _set_cookie(response: Response, key: str, value: str, max_age: int | None = None):
    response.set_cookie(
        key,
        value,
        max_age=max_age,
        httponly=True,
        samesite="strict",
        secure=get_settings().cookie_secure,
        path="/",
    )


def _render(request: Request, name: str, status_code: int = 200, **ctx) -> Response:
    token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
    response = templates.TemplateResponse(
        request,
        name,
        {"csrf_token": token, "statuses": list(BugStatus), "priorities": list(BugPriority), **ctx},
        status_code=status_code,
    )
    _set_cookie(response, CSRF_COOKIE, token)
    return response


def render_error(request: Request, status_code: int, detail: str) -> Response:
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return _redirect("/ui/login")
    return _render(request, "error.html", status_code=status_code, detail=detail)


def _check_csrf(request: Request, form_token: str) -> None:
    cookie = request.cookies.get(CSRF_COOKIE)
    if not cookie or not form_token or not secrets.compare_digest(cookie, form_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return user_from_token(request.cookies.get(SESSION_COOKIE), db)


def _require_user(user: User | None = Depends(_current_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return user


def _errors(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]


# --- auth ------------------------------------------------------------------


@router.get("/login")
def login_page(request: Request, user: User | None = Depends(_current_user)):
    if user:
        return _redirect("/ui")
    return _render(request, "login.html")


@router.post("/login")
def login(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not verify_password(password, user.password_hash if user else None):
        return _render(
            request, "login.html", status_code=401, email=email,
            errors=["Nieprawidłowy e-mail lub hasło."],
        )
    response = _redirect("/ui")
    _set_cookie(
        response, SESSION_COOKIE, create_access_token(user.id),
        max_age=get_settings().access_token_minutes * 60,
    )
    return response


@router.get("/register")
def register_page(request: Request):
    return _render(request, "register.html")


@router.post("/register")
def register(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    _check_csrf(request, csrf_token)
    try:
        data = UserCreate(email=email.strip(), password=password)
    except ValidationError as exc:
        return _render(request, "register.html", status_code=422, email=email, errors=_errors(exc))
    db.add(User(email=data.email.lower(), password_hash=hash_password(data.password)))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _render(
            request, "register.html", status_code=409, email=email,
            errors=["Ten e-mail jest już zarejestrowany."],
        )
    return _redirect("/ui/login")


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form("")):
    _check_csrf(request, csrf_token)
    response = _redirect("/ui/login")
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# --- bugs ------------------------------------------------------------------


@router.get("")
def bug_list(
    request: Request,
    status_filter: BugStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(_require_user),
):
    items = bugs.list_bugs(db, limit=100, status_filter=status_filter)
    return _render(request, "bugs.html", user=user, bugs=items, status_filter=status_filter)


@router.get("/bugs/new")
def new_bug_page(request: Request, user: User = Depends(_require_user)):
    return _render(request, "bug_form.html", user=user, bug=None, form={})


@router.post("/bugs/new")
def create_bug(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    priority: str = Form("medium"),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_user),
):
    _check_csrf(request, csrf_token)
    form = {"title": title, "description": description, "priority": priority}
    try:
        data = BugCreate(**form)
    except ValidationError as exc:
        return _render(
            request, "bug_form.html", status_code=422, user=user, bug=None,
            form=form, errors=_errors(exc),
        )
    bug = Bug(**data.model_dump(), reporter_id=user.id)
    db.add(bug)
    db.commit()
    return _redirect(f"/ui/bugs/{bug.id}")


@router.get("/bugs/{bug_id}")
def bug_detail(
    request: Request,
    bug_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_user),
):
    bug = bugs.get_bug_or_404(bug_id, db)
    return _render(request, "bug_detail.html", user=user, bug=bug)


@router.get("/bugs/{bug_id}/edit")
def edit_bug_page(
    request: Request,
    bug_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_user),
):
    bug = bugs.get_bug_or_404(bug_id, db)
    bugs.require_owner(bug, user)
    form = {
        "title": bug.title, "description": bug.description,
        "priority": bug.priority.value, "status": bug.status.value,
    }
    return _render(request, "bug_form.html", user=user, bug=bug, form=form)


@router.post("/bugs/{bug_id}/edit")
def edit_bug(
    request: Request,
    bug_id: int,
    title: str = Form(""),
    description: str = Form(""),
    priority: str = Form("medium"),
    status_: str = Form("open", alias="status"),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_user),
):
    _check_csrf(request, csrf_token)
    bug = bugs.get_bug_or_404(bug_id, db)
    bugs.require_owner(bug, user)
    form = {"title": title, "description": description, "priority": priority, "status": status_}
    try:
        data = BugUpdate(**form)
    except ValidationError as exc:
        return _render(
            request, "bug_form.html", status_code=422, user=user, bug=bug,
            form=form, errors=_errors(exc),
        )
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(bug, field, value)
    db.commit()
    return _redirect(f"/ui/bugs/{bug.id}")


@router.post("/bugs/{bug_id}/delete")
def delete_bug(
    request: Request,
    bug_id: int,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(_require_user),
):
    _check_csrf(request, csrf_token)
    bug = bugs.get_bug_or_404(bug_id, db)
    bugs.require_owner(bug, user)
    db.delete(bug)
    db.commit()
    return _redirect("/ui")
