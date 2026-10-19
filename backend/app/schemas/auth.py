from pydantic import BaseModel, Field

from app.schemas.user import UserResponse


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=255)


class LoginResponse(BaseModel):
    """统一响应格式：code=200 成功，其他为业务错误（HTTP 状态码仍是 200）。"""
    token:str
    user: UserResponse


class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str | None = None
