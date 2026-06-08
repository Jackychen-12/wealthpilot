"""认证路由 — 注册/登录/获取当前用户。"""

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlmodel import Session, select

from wealthpilot.models.user import User
from wealthpilot.services.auth import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_session)):
    existing = db.exec(select(User).where(User.username == req.username)).first()
    if existing:
        raise HTTPException(400, "用户名已存在")
    if len(req.password) < 4:
        raise HTTPException(400, "密码至少4位")

    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token, user_id=user.id, username=user.username)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_session)):
    user = db.exec(select(User).where(User.username == req.username)).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(401, "用户名或密码错误")

    token = create_access_token(user.id, user.username)
    return TokenResponse(access_token=token, user_id=user.id, username=user.username)


@router.get("/me", response_model=UserResponse)
def get_me(authorization: str = Header(default=""), db: Session = Depends(get_session)):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    if not token:
        raise HTTPException(401, "未提供认证 token")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(401, "token 无效或已过期")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(404, "用户不存在")
    return UserResponse(id=user.id, username=user.username, email=user.email)
