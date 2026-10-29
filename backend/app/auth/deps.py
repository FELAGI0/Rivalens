"""FastAPI dependency: current user from Bearer token."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_token
from app.db.session import get_session
from app.models import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_session),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    subject = decode_token(credentials.credentials)
    if subject is None:
        raise unauthorized
    user = db.get(User, _uuid_or_none(subject))
    if user is None:
        raise unauthorized
    return user


def _uuid_or_none(value: str):
    import uuid

    try:
        return uuid.UUID(value)
    except ValueError:
        return None
