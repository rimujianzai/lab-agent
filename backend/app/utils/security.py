from datetime import datetime, timedelta
import jwt
from app.config import settings

# 注意：本文件不能叫 jwt.py。它和第三方包 jwt 同名时，`import jwt` 会解析到自己，
# 于是 jwt.encode / jwt.decode 变成「不是模块 jwt 的已知属性」，运行时也容易导入错包。


def create_access_token(user_id: int) -> str:
    """创建JWT token"""
    expire = datetime.now() + timedelta(hours=settings.JWT_EXPIRE_HOURS)

    payload = {"user_id": user_id, "exp": expire}  # exp是固定key，不能写成别的

    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_access_token(token: str) -> dict:
    """解析jwt token"""
    return jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
