from datetime import datetime
import json
from sqlalchemy.orm import Session, joinedload
from langchain_core.tools import tool

from app.common.exceptions import BusinessException
from app.models.lab import Lab
from app.models.reservation import Reservation
from app.models.user import User
from app.schemas.reservation import ReservationCreateRequest
from app.services import equipment_service, kb_service, lab_service, reservation_service


def build_tools(db: Session, current_user: User):

    @tool
    def search_lab_docs(query: str) -> str:
        """根据用户的提问检索知识库"""
        try:
            return kb_service.search(query) or "没有检索到相关的资料"
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @tool
    def list_open_labs(keywords: str = "") -> str:
        """查询开放的实验室列表"""
        try:
            # 单独存一个变量：keywords 声明成了 str，直接赋 None 会被类型检查拦住
            kw = keywords.strip() or None
            page = lab_service.get_lab_page_list(
                db, page=1, page_size=10, keywords=kw, status=1
            )
            rows = [
                {
                    "id": item.id,
                    "name": item.name,
                    "location": item.location,
                    "capacity": item.capacity,
                    "open_time": item.open_time,
                    "close_time": item.close_time,
                }
                for item in page.list
            ]
            return json.dumps({"total": page.total, "labs": rows}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @tool
    def list_lab_equipments(lab_id: int, keywords: str = "") -> str:
        """查询某个实验室的设备列表"""
        try:
            kw = keywords.strip() or None
            page = equipment_service.get_equipment_page_list(
                db, page=1, page_size=10, lab_id=int(lab_id), keywords=kw
            )
            rows = [
                {
                    "id": item.id,
                    "name": item.name,
                    "lab_id": item.lab_id,
                    "lab_name": item.lab_name,
                    "spec": item.spec,
                    "quantity": item.quantity,
                    "status": item.status,
                }
                for item in page.list
            ]
            return json.dumps(
                {"total": page.total, "equipments": rows}, ensure_ascii=False
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @tool
    def create_lab_reservation(
        lab_id: int,
        date: str,
        start_time: str,
        end_time: str,
        equipment_id: int | None = None,
        remark: str | None = None,
    ) -> str:
        """创建预约单预约实验室或设备"""
        try:
            # create_reservation 要的是请求 schema，不是 ORM 模型：
            # 传 ORM 对象只是「碰巧字段名一样」才能跑，而且会绕过 pydantic 的参数校验
            data = ReservationCreateRequest(
                lab_id=lab_id,
                equipment_id=equipment_id,
                date=date,
                start_time=start_time,
                end_time=end_time,
                remark=remark,
            )
            reservation_service.create_reservation(db, current_user, data)
            return json.dumps(
                {
                    "ok": True,
                    "message": "预约已提交，请等待管理员审核",
                    "lab_id": lab_id,
                    "equipment_id": equipment_id,
                    "date": date,
                    "start_time": start_time,
                    "end_time": end_time,
                },
                ensure_ascii=False,
            )
        except BusinessException as exc:
            return json.dumps({"ok": False, "error": exc.message}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @tool
    def get_today() -> str:
        """获取服务器当前的日期  2026-09-20"""
        now = datetime.now()
        return now.strftime("%Y-%m-%d")

    @tool
    def list_my_reservations(status: int | None = None, limit: int = 5) -> str:
        """查询当前登录用户自己的预约记录，可按状态过滤

        status: 0待审核 1已通过 2已拒绝 3已取消，不传则返回全部
        limit: 最多返回几条，默认 5
        """
        try:
            # 这里刻意不把 user_id 做成参数。
            # 一旦它是参数，模型就可能被「帮我查一下 user_id=3 的预约」这类话术
            # 诱导着填别人的 id —— 等于把越权查询的口子直接交给 LLM。
            # 身份只能来自闭包捕获的 current_user，模型既看不见也改不了。
            query = (
                db.query(Reservation)
                # 关联的实验室/设备名要在返回里展示，用 joinedload 一次性带出来，
                # 否则每条记录都会各触发一次懒加载查询（N+1）
                .options(
                    joinedload(Reservation.lab),
                    joinedload(Reservation.equipment),
                )
                .filter(Reservation.user_id == current_user.id)
            )
            if status is not None:
                query = query.filter(Reservation.status == int(status))
            # 按日期倒序：用户最关心的是最近和即将到来的预约
            items = (
                query.order_by(
                    Reservation.date.desc(), Reservation.start_time.desc()
                )
                .limit(max(1, min(int(limit), 20)))
                .all()
            )
            if not items:
                return json.dumps(
                    {"total": 0, "reservations": [], "message": "当前没有预约记录"},
                    ensure_ascii=False,
                )
            status_text = {0: "待审核", 1: "已通过", 2: "已拒绝", 3: "已取消"}
            rows = [
                {
                    "id": item.id,
                    "type": "设备" if item.equipment_id else "实验室",
                    "lab_name": item.lab.name if item.lab else None,
                    "equipment_name": item.equipment.name if item.equipment else None,
                    "date": item.date,
                    "start_time": item.start_time,
                    "end_time": item.end_time,
                    "status": item.status,
                    "status_text": status_text.get(item.status, "未知"),
                    "remark": item.remark,
                }
                for item in items
            ]
            return json.dumps(
                {"total": len(rows), "reservations": rows}, ensure_ascii=False
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @tool
    def get_lab_open_hours(lab_id: int | None = None, keywords: str = "") -> str:
        """查询实验室的开放时间

        lab_id: 指定实验室 ID，只查这一个
        keywords: 不给 lab_id 时，按实验室名称模糊搜索
        两个都不给则返回前 10 个实验室
        """
        try:
            query = db.query(Lab)
            if lab_id is not None:
                query = query.filter(Lab.id == int(lab_id))
            elif keywords.strip():
                query = query.filter(Lab.name.like(f"%{keywords.strip()}%"))
            labs = query.limit(10).all()
            if not labs:
                return json.dumps(
                    {"total": 0, "labs": [], "message": "没有找到匹配的实验室"},
                    ensure_ascii=False,
                )
            rows = [
                {
                    "id": item.id,
                    "name": item.name,
                    "location": item.location,
                    "open_time": item.open_time,
                    "close_time": item.close_time,
                    "status": item.status,
                    "status_text": "开放" if item.status == 1 else "已关闭",
                }
                for item in labs
            ]
            return json.dumps(
                {
                    "total": len(rows),
                    "labs": rows,
                    # 把这条一起带上：开放时间只说明「什么时候能来」，
                    # 不代表可以直接进门，漏了这句用户容易误以为不用预约
                    "note": "开放时间内仍需先预约并通过审核，不能直接进入",
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    return [
        search_lab_docs,
        list_open_labs,
        list_lab_equipments,
        create_lab_reservation,
        get_today,
        list_my_reservations,
        get_lab_open_hours,
    ]
