from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from app.auth.rbac import user_has_permission
from app.database import get_db
from app.models.entities import ADGroup, User


def get_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_user_optional(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user


def require_permission(user: User, permission: str, db: Session | None = None) -> None:
    if db is not None:
        user = (
            db.query(User)
            .options(joinedload(User.ad_groups).joinedload(ADGroup.permissions))
            .filter(User.id == user.id)
            .first()
        ) or user
    if not user_has_permission(user, permission):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
