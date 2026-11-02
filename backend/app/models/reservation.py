from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.equipment import Equipment
from app.models.lab import Lab
from app.models.user import User


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        # 冲突检测的查询形状是「lab_id + date + equipment_id 等值，start_time 范围」，
        # 这个索引让前三个等值列走最左前缀定位，再用 start_time 收窄扫描范围。
        # 它的作用不只是查询快：InnoDB 的行锁是加在索引记录上的，
        # 没有这条索引时条件只能全表扫描，SELECT ... FOR UPDATE 会退化成锁全表。
        Index(
            "idx_lab_date_equip_start",
            "lab_id",
            "date",
            "equipment_id",
            "start_time",
        ),
        # 60 秒兜底扫描按 status 过滤，单独给一个索引避免全表扫
        Index("idx_status", "status"),
        {"comment": "预约信息"},
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), comment="预约人", nullable=False
    )
    lab_id: Mapped[int] = mapped_column(
        ForeignKey("labs.id"), comment="实验室", nullable=False
    )
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id"), comment="设备，空表示预约实验室", nullable=True
    )
    date: Mapped[str] = mapped_column(String(20), comment="预约日期", nullable=False)
    start_time: Mapped[str] = mapped_column(
        String(20), comment="开始时间", nullable=False
    )
    end_time: Mapped[str] = mapped_column(
        String(20), comment="结束时间", nullable=False
    )
    remark: Mapped[str] = mapped_column(String(255), comment="备注", nullable=True)
    status: Mapped[int] = mapped_column(
        comment="预约状态 0待审核，1已通过，2已拒绝，3已取消", default=0
    )

    user: Mapped[User] = relationship()
    lab: Mapped[Lab] = relationship()
    equipment: Mapped[Equipment] = relationship()
