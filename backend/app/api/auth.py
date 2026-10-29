"""Auth endpoints: register, login, me."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.session import get_session
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    plan: str

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(id=user.id, email=user.email, plan=str(user.plan))


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_session)) -> User:
    existing = db.scalars(
        select(User).where(User.email == payload.email)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="email already registered")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        plan="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_session)) -> TokenOut:
    user = db.scalars(
        select(User).where(User.email == payload.email)
    ).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="wrong email or password")
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.from_user(user)
