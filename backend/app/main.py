from contextlib import asynccontextmanager
from app.database import init_db
from app.api import api
from app.config import settings
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import UPLOAD_DIR
import asyncio
import logging
from app.services import reservation_service, kb_service
from app.common.exceptions import (
    BusinessException,
    business_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    global_exception_handler,
)

logger = logging.getLogger("lab_agent")

# 只配置 lab_agent 这一个 logger，不动根 logger。
# 用 logging.basicConfig 会把 uvicorn、sqlalchemy 等第三方库的日志一起放开，噪音很大。
# 级别用 DEBUG 是为了能看到 kb_service 检索命中了哪些片段，上线可以改成 INFO。
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.DEBUG)


# 建表。这里刻意不用裸的 Base.metadata.create_all：
# 建表阶段一旦抛异常，uvicorn 工作进程会直接退出，而端口已被父进程占住，
# 于是出现「端口被占用(10048) + 请求连不上」的假死。
# init_db() 内部把错误记进日志并返回 False，让服务照常启动、由接口返回明确错误。
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 预热向量库：模型加载（约 8s）挪到启动阶段，避免首个请求超过前端 30s 超时
    try:
        # 这个超时是必要的兜底：预热会碰网络（SentenceTransformer 默认要去
        # huggingface.co 核对模型文件），网络一旦卡住，这里又是 await，
        # 整个启动就永远停住 —— 端口不监听、前端所有请求失败，而日志里只有
        # 一句 "Waiting for application startup."，极难定位。
        # 超时后加载线程仍在后台跑完，只是不再挡着服务起来。
        await asyncio.wait_for(asyncio.to_thread(kb_service.warmup), timeout=60)
    except Exception:
        logger.exception("向量库预热失败（或超时），服务继续启动")
    # 启动项目开启异步的扫描任务
    task = asyncio.create_task(reservation_service.run_expire_scan())
    yield
    task.cancel()  # 关闭项目同时取消异步任务


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,  # 允许的前端源，来自 config.py 的 CORS_ORIGINS
    # Vite 启动时如果 5173 被占用会自动顺延到 5174、5175……，
    # 端口号写死就会出现「后端明明活着，浏览器却报网络异常」的跨域假象，
    # 所以本地开发统一用正则放行 localhost / 127.0.0.1 的任意端口。
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,  # ✅ 关键：允许前端携带 Authorization token
    allow_methods=["*"],  # 允许所有请求方法 GET POST PUT DELETE OPTIONS
    allow_headers=["*"],  # 允许所有请求头（包含Authorization）
)
app.include_router(api)
# 注册异常处理器
app.add_exception_handler(BusinessException, business_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
# 全局的异常兜底，必须放在最后注册！！
app.add_exception_handler(Exception, global_exception_handler)

# 挂载静态资源：/uploads/xxx.jpg → uploads/xxx.jpg
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/")
def root():
    return {"message": "Hello World"}
