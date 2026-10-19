from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.response import Response
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import conversation_service

router = APIRouter(prefix="/ai/conversation", tags=["AI对话历史相关接口"])


@router.get("/list")
def get_conversation_list(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    res = conversation_service.get_conversation_page_list(db, current_user, page, page_size)
    return Response.success(data=res)


@router.get("/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    res = conversation_service.get_conversation_messages(db, current_user, conversation_id)
    return Response.success(data=res)


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation_service.delete_conversation(db, current_user, conversation_id)
    return Response.success(message="删除成功")
