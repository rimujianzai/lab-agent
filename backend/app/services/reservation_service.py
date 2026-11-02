from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from datetime import datetime
from app.common.response import PageResponse
from app.schemas.reservation import ReservationCreateRequest, ReservationResponse
from app.common.exceptions import BusinessException
from app.models.equipment import Equipment
from app.models.lab import Lab
from app.models.reservation import Reservation
from app.models.user import User
import asyncio
from app.database import SessionLocal

def get_reservation_page_list(
    db: Session,
    current_user: User,
    page: int,
    page_size: int,
    status: int | None = None,
):
    """查询预约的记录"""
    query = db.query(Reservation)
    if current_user.role != "admin":
        query = query.filter(Reservation.user_id == current_user.id)
    if status is not None:
        query = query.filter(Reservation.status == status)
    total = query.count()
    items = (
        query.order_by(Reservation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    result = []
    for item in items:
        res = ReservationResponse.model_validate(item)
        res.user_name = item.user.name if item.user else None
        res.lab_name = item.lab.name if item.lab else None
        res.equipment_name = item.equipment.name if item.equipment else None
        res.type = "设备" if item.equipment_id else "实验室"
        result.append(res)
    return PageResponse(list=result, total=total)


def cancel_reservation(db: Session, current_user: User, reservation_id: int):
    """学生取消预约"""
    item = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not item:
        raise BusinessException(message="预约记录不存在")
    if item.user_id != current_user.id:
        raise BusinessException(message="无权限", code=403)
    if item.status != 0:
        raise BusinessException(message="当前状态无法取消")
    item.status = 3
    db.commit()


def audit_reservation(db: Session, reservation_id: int, status: int):
    """管理员审核预约"""
    if status not in [1, 2]:
        raise BusinessException(message="审核状态错误")
    item = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not item:
        raise BusinessException(message="预约记录不存在")
    if item.status != 0:
        raise BusinessException(message="当前状态不支持审核")
    item.status = status
    db.commit()


def create_reservation(db: Session, current_user: User, data: ReservationCreateRequest):
    """创建预约记录"""
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")
    if data.date < current_date:
        raise BusinessException(message="预约日期不能小于当前的日期")
    if data.end_time < data.start_time:
        raise BusinessException(message="预约的结束时间不能小于开始时间")
    if data.date == current_date and data.start_time < current_time:
        raise BusinessException(message="预约开始时间不能小于当前的时间")
    lab = db.query(Lab).filter(Lab.id == data.lab_id).first()
    if not lab:
        raise BusinessException(message="实验室不存在")
    if lab.status != 1:
        raise BusinessException(message="实验室已关闭")
    if lab.open_time and data.start_time < lab.open_time:
        raise BusinessException(message="预约时间不能早于实验室的开放时间")
    if lab.close_time and data.end_time > lab.close_time:
        raise BusinessException(message="预约时间不能晚于实验室的关闭时间")

    # equipment_id 不为空 则表示这次是预约的实验室设备
    if data.equipment_id:
        equipment = (
            db.query(Equipment).filter(Equipment.id == data.equipment_id).first()
        )
        if not equipment:
            raise BusinessException(message="实验室设备不存在")
        if equipment.status != 1:
            raise BusinessException(message="实验室设备正在维修")

    # 实验室或者设备是否是可预约的状态
    #
    # 「加锁查询 + 插入」必须在同一个事务里完成。不加锁时这是典型的
    # check-then-act：先查有没有冲突、再插入，两个请求并发会这样交错
    #   A 查 10:00-11:00 无冲突 → B 查 10:00-11:00 也无冲突
    #   → A 插入 → B 插入
    # 结果是同一时段被约了两次。原因是 A 插入前 B 的查询根本看不见 A 的行。
    #
    # with_for_update() 生成 SELECT ... FOR UPDATE。InnoDB 在 REPEATABLE READ
    # 隔离级别下加的是 next-key lock（记录锁 + 间隙锁）：不仅锁住已命中的记录，
    # 连「将要插入的那个间隙」一起锁住。另一个事务想往同一区间插入时会被阻塞，
    # 等本事务提交后重新查一次才发现冲突，于是被拒绝。
    #
    # 两个前提缺一不可：
    #   1) 条件必须走索引，否则全表扫描会让行锁退化成锁全表（见模型上的
    #      idx_lab_date_equip_start）
    #   2) 隔离级别必须是 RR 或以上，READ COMMITTED 下间隙锁失效，防不住幻读
    #
    # 用 .all() 而不是 .first()：让扫描完整覆盖候选区间，间隙锁才会把区间
    # 两端都锁上，不会在第一条记录处提前停止。
    query = (
        db.query(Reservation)
        .filter(
            Reservation.lab_id == data.lab_id,
            Reservation.date == data.date,
            Reservation.status.in_([0, 1]),  # 0表示待审核  1已通过
            Reservation.start_time < data.end_time,
            Reservation.end_time > data.start_time,
        )
        .with_for_update()
    )
    if data.equipment_id:
        query = query.filter(
            Reservation.equipment_id == data.equipment_id
        )  # 预约实验室设备
    else:
        query = query.filter(Reservation.equipment_id.is_(None))  # 只预约实验室
    try:
        conflicts = query.all()
    except OperationalError:
        # 锁等待超时（默认 innodb_lock_wait_timeout=50s）或死锁被 MySQL 回滚。
        # 这里必须显式回滚，把事务和锁一起放掉，再把原始错误转成可读提示。
        db.rollback()
        raise BusinessException(message="当前预约人数较多，请稍后重试")
    if conflicts:
        # 抛异常向上传播，get_db() 里会 rollback，锁随之释放
        raise BusinessException(message="该时段已预约")

    reservation_model = Reservation(
        user_id=current_user.id,
        lab_id=data.lab_id,
        equipment_id=data.equipment_id,
        date=data.date,
        start_time=data.start_time,
        end_time=data.end_time,
        remark=data.remark,
        status=0,
    )
    try:
        db.add(reservation_model)
        db.commit()
    except Exception:
        # 提交失败必须回滚，否则这把锁会一直挂到连接被回收才释放
        db.rollback()
        raise


def expire_pending_reservations():
    db = SessionLocal()
    try:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        now_time = now.strftime("%H:%M")
        items = db.query(Reservation).filter(Reservation.status == 0).all()
        changed = False
        for item in items:
            if item.date < today or (item.date == today and item.end_time <= now_time):
                item.status = 3
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()


async def run_expire_scan():
    while True:
        expire_pending_reservations()
        await asyncio.sleep(60)
