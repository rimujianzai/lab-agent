from datetime import datetime

from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.models.conversation import ChatMessage, Conversation
from app.models.user import User
from app.schemas.conversation import ChatMessageResponse, ConversationResponse

# 会话标题取提问的前多少个字
TITLE_LENGTH = 30


def get_owned_conversation(
    db: Session, current_user: User, conversation_id: int
) -> Conversation:
    """查会话，并校验它属于当前用户。

    归属校验不能省：只按 id 查的话，把 id 换成别人的就能读到别人的聊天记录。
    """
    conversation = (
        db.query(Conversation).filter(Conversation.id == conversation_id).first()
    )
    if not conversation:
        raise BusinessException(message="会话不存在")
    if conversation.user_id != current_user.id:
        raise BusinessException(message="无权访问该会话", code=403)
    return conversation


def create_conversation(db: Session, current_user: User, title: str) -> Conversation:
    """新建会话，标题直接用第一条提问的开头"""
    # " ".join(split()) 会把换行、连续空格一起拍平，
    # 不然带换行的提问会把侧边栏的单行标题撑成好几行
    title = " ".join(title.split())[:TITLE_LENGTH] or "新对话"
    conversation = Conversation(user_id=current_user.id, title=title)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def add_message(db: Session, conversation: Conversation, role: str, content: str):
    """往会话里追加一条消息"""
    db.add(ChatMessage(conversation_id=conversation.id, role=role, content=content))
    # 顺手把会话顶到最前。update_time 只在 Conversation 这一行被 UPDATE 时
    # 才自动刷新，光加消息不会碰它，不手动改的话历史列表永远不重排。
    conversation.update_time = datetime.now()
    db.commit()


def get_conversation_page_list(
    db: Session, current_user: User, page: int, page_size: int
):
    # 只看自己的会话，别人的不返回
    query = db.query(Conversation).filter(Conversation.user_id == current_user.id)
    total = query.count()
    items = (
        # 最近聊过的排最前；id 兜底，防止同一秒建的会话顺序乱跳
        query.order_by(Conversation.update_time.desc(), Conversation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PageResponse(
        list=[ConversationResponse.model_validate(item) for item in items], total=total
    )


def get_conversation_messages(
    db: Session, current_user: User, conversation_id: int
) -> list[ChatMessageResponse]:
    conversation = get_owned_conversation(db, current_user, conversation_id)
    items = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation.id)
        # 正序：对话是从上往下读的，倒序到了前端还得再翻回来
        .order_by(ChatMessage.id.asc())
        .all()
    )
    return [ChatMessageResponse.model_validate(item) for item in items]


def delete_conversation(db: Session, current_user: User, conversation_id: int):
    conversation = get_owned_conversation(db, current_user, conversation_id)
    db.delete(conversation)  # 配了 cascade，底下的消息会一起删
    db.commit()
