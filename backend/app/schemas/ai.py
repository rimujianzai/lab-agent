from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    # 不带表示这是一轮新对话，后端会自动建一个会话并把 id 回给前端
    conversation_id: int | None = None
