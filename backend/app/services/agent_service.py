from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from sqlalchemy.orm import Session
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
import logging
from collections.abc import AsyncIterator
from typing import Any
from app.common.exceptions import BusinessException
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.ai import ChatRequest
from app.services import agent_tools, conversation_service
from app.config import settings

logger = logging.getLogger("lab_agent")

SYSTEM_PROMPT = """你是智能实验室预约系统的 Agent，回答要简洁。
你可以：
1. 使用 search_lab_docs 查询实验室的规则、安全、开放时间等问题
2. 使用 list_open_labs / list_lab_equipments  查询真实的实验室和设备
3. 再用户进行了预约确认后，使用 create_lab_reservation 来进行真实的预约落库
4. 使用 get_today 来进行日期的换算

## 必须遵守
当用户提到了 今天、明天、后天 等日期相关的问题，请先调用 get_today 来获取日期，**不要直接返回 我需要确定明天的具体日期**。

在提交预约之前必须向用户复述：实验室ID与名称（或设备ID和名称）、日期、开始时间、结束时间。并得到用户确认再进行实际操作。
用户没说【确认】【确认预约】【就这样预约】等确定性回复之前，不要调用 create_lab_reservation。
工作流的确认环节里如果缺少了 lab_id，请先 list_open_labs 查到了 lab_id 再创建，不要瞎写。
工作流的确认环节里如果缺少了 equipment_id，请先 list_lab_equipments 查到了 equipment_id 再创建，不要瞎写。

预约成功后状态是待审核，必须管理员确认后实验室（或设备）才能使用。
不要瞎编数据库里没有的实验室或者设备信息。
如果是问开放时间或者实验室规则，优先调用 search_lab_docs，不要凭空回复。
"""


def message_text(message: BaseMessage) -> str:
    """把消息内容统一取成纯文本。

    langchain 的 content 是 str | list[str | dict] 的联合类型：
    纯文本对话给的是 str，多模态/带工具块时给的是列表（形如
    [{"type": "text", "text": "..."}]）。这里统一拍平成字符串，
    免得每个调用点都要自己判断一次。
    """
    content = message.content
    if isinstance(content, str):
        return content.strip()
    parts = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        else:
            parts.append(str(part.get("text", "")))
    return "".join(parts).strip()


def build_agent(db: Session, current_user: User):
    tools = agent_tools.build_tools(db, current_user)
    llm = ChatOpenAI(
        # ChatOpenAI 的这个字段声明成 SecretStr，直接塞 str 运行期没问题
        # （pydantic 会自动转换），但静态检查会报类型不匹配，所以这里显式包一层。
        api_key=SecretStr(settings.LLM_API_KEY),
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=0,
        streaming=True,  # 打开流式，stream_events 才能收到逐字 token
    ).bind_tools(tools)

    def agent_node(state: MessagesState):
        """langGraph 执行的工作流 的节点"""
        response = llm.invoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)  # 调用大模型的节点
    graph.add_node("tools", ToolNode(tools))  # tool call的节点
    graph.add_edge(START, "agent")  # 流程的起点，call LLM
    graph.add_conditional_edges(
        "agent", tools_condition
    )  # 看有无 tool_call  有就继续call  没有就END 输出
    graph.add_edge("tools", "agent")  # 让agent看tool调用的结果
    return graph.compile()


def run_agent(db: Session, current_user: User, data: ChatRequest) -> str:
    """大模型对话"""
    # 先建输入（顺带把空消息校验掉），免得参数不合法还白建一个会话
    inputs = _build_input(data)
    conversation = _resolve_conversation(db, current_user, data)
    conversation_service.add_message(db, conversation, "user", _last_user_text(data))

    agent = build_agent(db, current_user)
    try:
        result = agent.invoke(
            inputs,
            config={"recursion_limit": 10},
        )  # 设置对话循环的上限是10轮
    except BusinessException:
        raise
    except Exception:
        logger.exception("大模型调用失败")
        raise BusinessException(message="大模型调用失败，请稍后重试")

    messages = result.get("messages") or []
    if not messages:
        raise BusinessException(message="大模型没有任何返回内容")
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = message_text(message)
            if content:
                # 落库：下次打开这个会话才看得到这轮问答
                conversation_service.add_message(
                    db, conversation, "assistant", content
                )
                return content
    # 兜底：递归到上限时最后一条可能不是 AIMessage（比如停在工具节点上），
    # 如果不显式抛异常，函数会隐式返回 None，接口层拿到 None 才报错，很难查。
    raise BusinessException(message="大模型没有给出回答，请换个说法再试一次")

# 工具英文名 → 页面上给人看的中文过程文案
TOOL_LABELS = {
    "search_lab_docs": "检索实验室知识库",
    "list_open_labs": "查询开放实验室",
    "list_lab_equipments": "查询实验室设备",
    "create_lab_reservation": "提交预约",
    "get_today": "获取今天日期",
}


def _chunk_text(chunk: Any) -> str:
    """从模型流式 chunk 里抠出纯文本。
    content 有时是 str，有时是 [{type, text}, ...] 这种块列表，要统一成字符串。
    """
    if chunk is None:
        return ""
    # chunk 可能是 AIMessageChunk，真正字在 .content
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(part.get("text") or "")
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return str(content) if content is not None else ""


def _tool_output_preview(output: Any, limit: int = 200) -> str:
    """把工具结果收成短预览，避免整段 JSON 刷到前端过程区。"""
    # LangGraph 里工具结果经常是 ToolMessage，正文在 .content
    if isinstance(output, ToolMessage):
        output = output.content
    text = output if isinstance(output, str) else str(output)
    # 太长就截断，末尾加省略号
    return text if len(text) <= limit else text[:limit] + "…"


def _build_input(data: ChatRequest) -> MessagesState:
    """把前端传来的文本消息转成 LangChain 消息，再包成图的输入状态。

    返回 MessagesState 而不是裸 dict：stream_events 的重载要求 input 是
    MessagesState | Command | None，裸 dict 推不出来。

    history 显式标成 list[AnyMessage] 也是同一个原因：不标的话元素会被推成
    "SystemMessage | HumanMessage | AIMessage" 这样一个更窄的联合，而 list
    是不变（invariant）的，装不进 MessagesState 里的 list[AnyMessage]。
    """
    if not data.messages:
        raise BusinessException(message="对话内容为空")
    history: list[AnyMessage] = []
    for message in data.messages:
        if message.role == "user" and message.content.strip():
            history.append(HumanMessage(content=message.content.strip()))
        elif message.role == "assistant" and message.content.strip():
            history.append(AIMessage(content=message.content.strip()))
    if not history:
        raise BusinessException(message="请输入您要对话的内容")
    return {"messages": [SystemMessage(content=SYSTEM_PROMPT), *history]}


def _last_user_text(data: ChatRequest) -> str:
    """取用户最新的一条提问。

    前端会把整段历史都发过来，所以要倒着找第一条 user 消息，
    不能直接取 messages[-1]（它可能是助手刚答完的那条）。
    """
    for message in reversed(data.messages or []):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""


def _resolve_conversation(
    db: Session, current_user: User, data: ChatRequest
) -> Conversation:
    """确定这一轮挂在哪个会话下：带了 id 就复用，没带就新建一个。

    没有单独的「新建会话」接口，新会话是在第一条消息落地时才建的，
    这样历史列表里不会堆一堆说完「你好」就没人管的空会话。
    """
    if data.conversation_id:
        return conversation_service.get_owned_conversation(
            db, current_user, data.conversation_id
        )
    return conversation_service.create_conversation(
        db, current_user, _last_user_text(data)
    )


async def stream_agent(
    db: Session, current_user: User, data: ChatRequest
) -> AsyncIterator[dict]:
    """异步生成器：边跑 Agent 边 yield 事件，供 SSE 推给前端。
    事件类型：conversation / status / tool_start / tool_end / token / done / error

    这里必须用 astream_events 而不是 stream_events(version="v2")：
    Pregel 上的 stream_events 只实现了实验性的 v3 协议，v1/v2 会直接抛
    NotImplementedError，而 v3 的事件结构和下面的取值方式完全不同。
    另外 astream_events 只有异步版本，所以整个生成器是 async 的。
    """
    try:
        # 先建输入（顺带把空消息校验掉），免得参数不合法还白建一个会话
        inputs = _build_input(data)
        conversation = _resolve_conversation(db, current_user, data)
        # 前端要靠这个 id 才知道「新对话」该切到哪个会话上
        yield {
            "type": "conversation",
            "id": conversation.id,
            "title": conversation.title,
        }
        conversation_service.add_message(db, conversation, "user", _last_user_text(data))

        agent = build_agent(db, current_user)
        # yield = 先交出这一条，函数暂停；前端收到后再继续往下跑
        yield {"type": "status", "message": "正在思考…"}
        # 攒着这一轮的助手回答，收尾时整体落库
        answer = ""
        # astream_events：图每走一步（调工具、吐字）都会冒出一个内部事件
        async for event in agent.astream_events(
            inputs,
            version="v2",
            config={"recursion_limit": 10},  # agent⇄tools 来回上限，防空转
        ):
            kind = event.get("event")
            if kind == "on_tool_start":
                name = event.get("name") or ""
                yield {
                    "type": "tool_start",
                    "name": name,
                    "label": TOOL_LABELS.get(name, name),  # 没有中文映射就退回英文名
                }
            elif kind == "on_tool_end":
                name = event.get("name") or ""
                yield {
                    "type": "tool_end",
                    "name": name,
                    "label": TOOL_LABELS.get(name, name),
                    # 只给预览；完整结果仍在图内部 messages 里给模型用
                    "preview": _tool_output_preview(
                        (event.get("data") or {}).get("output")
                    ),
                }
            elif kind == "on_chat_model_stream":
                # 只收 agent 节点的字；其它内部节点的噪声丢掉
                meta = event.get("metadata") or {}
                if meta.get("langgraph_node") not in (None, "agent"):
                    continue
                text = _chunk_text((event.get("data") or {}).get("chunk"))
                if text:
                    answer += text
                    yield {"type": "token", "content": text}
        # 收尾落库：等这一轮攒完再存，跟着 token 一条条存太碎
        if answer.strip():
            conversation_service.add_message(
                db, conversation, "assistant", answer.strip()
            )
        # 正常跑完：不要在 done 里再带一份全文，前端已经用 token 拼好了
        yield {"type": "done"}
    except BusinessException as exc:
        # 流已经是 SSE，错误也要用 yield，别 raise 成普通 JSON
        yield {"type": "error", "message": exc.message}
    except Exception:
        # 必须记日志：上面只给前端一句笼统的提示，不记的话真实原因（比如
        # 流式协议不支持、模型鉴权失败）就彻底查不到了。
        logger.exception("流式对话失败")
        yield {"type": "error", "message": "大模型调用失败，请稍后重试"}
