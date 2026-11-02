import logging
from datetime import datetime, timezone
from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings

logger = logging.getLogger("lab_agent")

# pool_pre_ping：每次从连接池取连接前先探活。
#   MySQL 默认 8 小时没活动就会单方面断开连接，没有这个参数的话，
#   隔一段时间再发请求会直接报 "MySQL server has gone away"（表现为接口 500）。
# pool_recycle：连接用满 1 小时就回收重建，比 MySQL 的 wait_timeout 更早，双保险。
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={"charset": "utf8mb4"},
    # 显式钉死 REPEATABLE READ。预约冲突检测靠 SELECT ... FOR UPDATE 的
    # 间隙锁（next-key lock）来防并发超卖，而间隙锁只在 RR 及以上生效：
    # 一旦被改成 READ COMMITTED，行锁只锁已存在的记录，另一个事务照样能
    # 往同一区间插入新行，冲突检测就形同虚设。
    # MySQL 默认就是 RR，但默认值可以被全局配置或连接串改掉，
    # 写在这里等于把这个前提固化进代码，不再依赖线上库怎么配。
    isolation_level="REPEATABLE READ",
)

# 数据库 session 会话的连接工厂
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# 兼容旧名字，其他地方仍在用 Session 的话不用改
Session = SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # 请求过程中出错时回滚，避免把脏会话还回连接池
        db.rollback()
        raise
    finally:
        db.close()


class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="主键ID", sort_order=-1
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间", sort_order=1
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        # 每次 UPDATE 自动刷新，不然改了数据 update_time 还是老值
        onupdate=lambda: datetime.now(timezone.utc),
        comment="更新时间",
        sort_order=2,
    )


def init_db() -> bool:
    """自动帮我们创建数据库和数据库表。

    返回是否成功。这里刻意不往上抛异常：
    一旦在建表阶段抛异常，uvicorn 的工作进程会立刻退出，
    但端口已经被父进程占住了，于是出现「端口被占用(10048) + 请求连不上」的假死状态。
    所以这里把错误记清楚、让服务照常启动，接口再返回明确的错误提示。
    """
    # 导入模型模块，确保所有表都注册到 Base.metadata 上
    from app import models  # noqa: F401  (仅为触发导入，本身不使用)

    try:
        Base.metadata.create_all(bind=engine)
        return True
    except Exception:
        logger.error(
            "建表失败：无法连接或操作数据库。\n"
            "  1) 确认 MySQL 服务已经启动\n"
            "  2) 确认 backend/.env 里的 DATABASE_URL 正确（库 lab_agent 需已创建）\n"
            "  3) 也可在项目根目录执行：mysql -uroot -p -e \"CREATE DATABASE IF NOT EXISTS lab_agent DEFAULT CHARSET utf8mb4;\"",
            exc_info=True,
        )
        return False
