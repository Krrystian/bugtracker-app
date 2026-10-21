"""Bug access rules shared by the JSON API and the web UI."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bug, BugStatus, User


def list_bugs(
    db: Session, limit: int = 50, offset: int = 0, status_filter: BugStatus | None = None
) -> list[Bug]:
    limit = max(1, min(limit, 100))
    stmt = select(Bug).order_by(Bug.id).limit(limit).offset(max(0, offset))
    if status_filter is not None:
        stmt = stmt.where(Bug.status == status_filter)
    return list(db.scalars(stmt).all())


def get_bug_or_404(bug_id: int, db: Session) -> Bug:
    bug = db.get(Bug, bug_id)
    if bug is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bug not found")
    return bug


def require_owner(bug: Bug, user: User) -> None:
    if bug.reporter_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the reporter can modify this bug")
