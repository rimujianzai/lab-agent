from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import User


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = {"comment": "AI 对话会话表"}

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), comment="所属用户", nullable=False
    )
    title: Mapped[str] = mapped_column(
        String(100), comment="会话标题，取第一条提问的前几个字", nullable=False
    )

    user: Mapped[User] = relationship()
    # cascade：删会话时把底下的消息一起删掉，不然会留一堆查不到的孤儿消息
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = {"comment": "AI 对话消息表"}

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), comment="所属会话", nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(20), comment="角色：user-用户，assistant-助手", nullable=False
    )
    # 用 Text 而不是项目里常见的 String(255)：助手回复动辄上千字，255 会插入失败
    content: Mapped[str] = mapped_column(Text, comment="消息内容", nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
