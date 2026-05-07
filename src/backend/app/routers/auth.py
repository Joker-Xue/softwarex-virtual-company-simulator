import os
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.email_verification import EmailVerificationToken
from app.models.user import User
from app.schemas.user import UserResponse
from app.utils.captcha import generate_captcha, verify_captcha
from app.utils.mail import send_verification_email
from app.utils.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_active_user,
    get_password_hash,
    verify_password,
)

router = APIRouter()

REVIEWER_MODE = os.getenv("REVIEWER_MODE", "false").lower() == "true"
REVIEWER_VERIFICATION_CODE = os.getenv("REVIEWER_VERIFICATION_CODE", "000000")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    full_name: str | None = Field(None, max_length=100)
    verification_code: str = Field(..., min_length=6, max_length=6)


class SendVerificationCodeRequest(BaseModel):
    email: EmailStr


@router.get("/captcha", summary="Get Captcha")
async def get_captcha():
    captcha_id, svg = generate_captcha()
    return {
        "captcha_id": captcha_id,
        "svg": svg,
        "expires_in": 300,
    }


@router.post("/send-verification-code", summary="Send registration email verification code")
async def send_verification_code(
    request: SendVerificationCodeRequest,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == request.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email is already registered")

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
    recent = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.email == request.email,
            EmailVerificationToken.created_at > cutoff,
        )
    )
    if recent.scalar_one_or_none():
        raise HTTPException(status_code=429, detail="Please wait 60 seconds before requesting another code")

    token_value = REVIEWER_VERIFICATION_CODE if REVIEWER_MODE else str(random.randint(100000, 999999))
    verification = EmailVerificationToken(
        email=request.email,
        token=token_value,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        used=False,
    )
    db.add(verification)
    await db.commit()

    if REVIEWER_MODE:
        return {
            "message": "Reviewer verification code generated.",
            "verification_code": token_value,
        }

    try:
        await send_verification_email(request.email, token_value)
    except Exception:
        raise HTTPException(status_code=503, detail="Email delivery failed. Please check SMTP configuration.")

    return {"message": "Verification code sent. Please check your email."}


@router.post("/register", summary="Register Account")
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(User).where((User.username == request.username) | (User.email == request.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already exists")

    verification = await db.execute(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.email == request.email)
        .order_by(EmailVerificationToken.created_at.desc())
    )
    token_row = verification.scalars().first()
    if token_row is None or token_row.used or token_row.token != request.verification_code:
        raise HTTPException(status_code=400, detail="Email verification code is invalid")
    if token_row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="email verification code has expired")

    token_row.used = True
    user = User(
        username=request.username,
        email=request.email,
        password_hash=get_password_hash(request.password),
        full_name=request.full_name,
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": UserResponse.model_validate(user),
    }


@router.post("/login", summary="User Login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    captcha_id: str = Query(...),
    captcha_code: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if not verify_captcha(captcha_id, captcha_code):
        raise HTTPException(status_code=400, detail="Verification code error")

    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="wrong username or password",
        )

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": UserResponse.model_validate(user),
    }


@router.get("/me", response_model=UserResponse, summary="Current User")
async def me(current_user: User = Depends(get_current_active_user)):
    return current_user
