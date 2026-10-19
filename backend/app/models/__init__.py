"""模型包：在这里导入所有模型，保证 Base.metadata 能收集到全部数据表。"""

from app.models.user import User

__all__ = ["User"]
