"""
用户相关 Pydantic 模型
"""
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


# ========== 基础模型 ==========
class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")
    phone: Optional[str] = Field(None, max_length=20, description="电话")


class UserInDB(UserBase):
    """数据库中的用户模型"""
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ========== 请求模型 ==========
class UserCreate(UserBase):
    """用户注册请求"""
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class UserLogin(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class UserUpdate(BaseModel):
    """用户更新请求"""
    full_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None


class UserPasswordChange(BaseModel):
    """修改密码请求"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


# ========== 响应模型 ==========
class UserResponse(UserBase):
    """用户信息响应"""
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RegisterResponse(UserResponse):
    """注册响应（含 access_token 支持自动登录）"""
    access_token: str


class UserProfileResponse(UserInDB):
    """用户完整资料响应"""
    pass


# ========== Token 模型 ==========
class Token(BaseModel):
    """Token响应"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # 30分钟


class TokenData(BaseModel):
    """Token数据"""
    user_id: Optional[int] = None
    username: Optional[str] = None
