from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.common.response import Response


class BusinessException(Exception):
    """自定义的业务异常"""

    def __init__(self, message: str, code: int = 500):
        self.message = message
        self.code = code
        super().__init__(message)


async def business_exception_handler(request: Request, exc: Exception):
    """自定义业务异常处理器

    参数标注成 Exception 而不是 BusinessException：Starlette 的
    ExceptionHandler 类型是 Callable[[Request, Exception], ...]，
    函数参数是逆变的，标注成更窄的类型会通不过类型检查。
    真正传入的一定是 BusinessException（按类型注册的），这里用 isinstance 收窄。
    """
    if not isinstance(exc, BusinessException):
        return await global_exception_handler(request, exc)
    return JSONResponse(
        status_code=200,
        content=Response.error(code=exc.code, message=exc.message).model_dump(),
    )


async def http_exception_handler(request: Request, exc: Exception):
    """Http异常处理器"""
    if not isinstance(exc, HTTPException):
        return await global_exception_handler(request, exc)
    return JSONResponse(
        status_code=exc.status_code,
        content=Response.error(code=exc.status_code, message=exc.detail).model_dump(),
    )


async def validation_exception_handler(request: Request, exc: Exception):
    """参数异常处理器

    只回一句「请求参数校验错误」的话，前端根本不知道该改哪个字段：
    上传接口少传 file、传成了 JSON、或者表单字段名拼错，返回的都是这一句。
    所以这里把 pydantic 的校验明细拼进 message，例如：
        请求参数校验错误：body.file: Field required
    """
    if not isinstance(exc, RequestValidationError):
        return await global_exception_handler(request, exc)
    details = "；".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    )
    return JSONResponse(
        status_code=422,
        content=Response.error(
            code=422, message=f"请求参数校验错误：{details}"
        ).model_dump(),
    )


async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    return JSONResponse(
        status_code=500,
        content=Response.error(code=500, message="服务器内部错误").model_dump(),
    )
