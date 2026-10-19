import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.common.response import Response
from app.database import get_db

logger = logging.getLogger("lab_agent")

router = APIRouter(tags=["系统相关接口"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """健康检查：同时确认服务和数据库是否正常。

    特意不加 get_current_user 依赖 —— 服务出问题时最需要用到它，
    这时候还要先登录就本末倒置了（还没登录的人也没法用它排查）。

    数据库挂了返回 503 而不是 200：顺手 curl 一下就能从状态码看出结果，
    不用去翻响应体里的 code。前端那边也会走到「数据库连接失败」这条提示上。
    """
    try:
        # 最轻量的探活：连不上数据库（MySQL 没起、密码错）这里就会抛异常
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("健康检查：数据库连接失败")
        return JSONResponse(
            status_code=503,
            content=Response.error(code=503, message="数据库连接失败").model_dump(),
        )
    return Response.success(message="服务正常", data={"database": "ok"})
