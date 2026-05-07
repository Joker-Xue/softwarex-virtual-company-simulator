"""
UserRelated Pydantic Model
"""
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


# ========== BaseModel ==========
class UserBase(BaseModel):
    """UserBaseModel"""
    username: str = Field(..., min_length=3, max_length=50, description="username")
    email: EmailStr = Field(..., description="email")
    full_name: Optional[str] = Field(None, max_length=100, description="full name")
    phone: Optional[str] = Field(None, max_length=20, description="phone")


class UserInDB(UserBase):
    """User Model in Database"""
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ========== askModel ==========
class UserCreate(UserBase):
    """userregisterask"""
    password: str = Field(..., min_length=6, max_length=100, description="password")


class UserLogin(BaseModel):
    """User Loginask"""
    username: str = Field(..., description="username or email")
    password: str = Field(..., description="password")


class UserUpdate(BaseModel):
    """User update ask"""
    full_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None


class UserPasswordChange(BaseModel):
    """Modify passwordask"""
    old_password: str = Field(..., description="old password")
    new_password: str = Field(..., min_length=6, max_length=100, description="new password")


# ========== Response Model ==========
class UserResponse(UserBase):
    """UserInfo response"""
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RegisterResponse(UserResponse):
    """register response（Contains access_token to support automatic login）"""
    access_token: str


class UserProfileResponse(UserInDB):
    """User complete profile response"""
    pass


# ========== Token Model ==========
class Token(BaseModel):
    """Token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # 30minutes


class TokenData(BaseModel):
    """Tokendata"""
    user_id: Optional[int] = None
    username: Optional[str] = None
