# 智能实验室预约系统（Lab Agent）

面向高校实验室场景的全栈预约系统：学生按日期与时段预约实验室 / 设备，管理员审核与维护基础数据，内置一个基于 **LangGraph + RAG + SSE** 的对话 Agent，用自然语言即可查规则、查空闲实验室并完成预约。

## ✨ 功能特点

- 🗓️ **完整预约闭环**：时段合法性校验 → 开放时间校验 → 冲突检测 → 提交待审核 → 管理员通过 / 拒绝 → 学生取消
- 🔐 **认证与权限**：JWT（PyJWT）+ bcrypt，学生 / 管理员两种角色，接口级依赖注入鉴权
- 🤖 **对话式预约**：LangGraph 状态图（agent ⇄ tools）+ 5 个工具，支持"查规则 → 查实验室 → 确认信息 → 落库"全流程
- 📚 **RAG 知识库**：Chroma 持久化向量库 + `BAAI/bge-small-zh-v1.5` 中文 Embedding，检索预约规则、安全规范、开放时间、设备使用说明
- ⚡ **SSE 流式对话**：逐字输出 token，并把「检索知识库 / 查询实验室 / 提交预约」等工具调用过程实时推给前端
- ⏱️ **超时自动失效**：后台 asyncio 任务每 60 秒扫描，把已过期仍未审核的预约置为已取消
- 📎 **文件上传**：实验室封面、设备图片上传，100MB 上限 + 扩展名白名单，静态目录直接挂载
- 🎨 **管理后台**：Vue 3 + Element Plus，实验室 / 设备 / 用户 / 预约审核 / AI 对话共 13 个页面
- 🧩 **统一契约**：所有接口统一 `{code, message, data}` 响应体，全局异常处理器兜底

## 🏗️ 技术栈

### 后端

- **Web 框架**：FastAPI 0.115 + Uvicorn
- **ORM / 数据库**：SQLAlchemy 2.0（`Mapped` 声明式）+ MySQL 8 + PyMySQL
- **数据校验**：Pydantic v2 + pydantic-settings（`.env` 注入配置）
- **Agent**：LangGraph（`StateGraph` + `ToolNode` + `tools_condition`）+ langchain-openai
- **RAG**：ChromaDB（PersistentClient）+ sentence-transformers
- **认证**：PyJWT + bcrypt
- **流式**：SSE（`text/event-stream`）

### 前端

- **框架**：Vue 3（组合式 API，JavaScript）
- **构建**：Vite 8
- **UI**：Element Plus + `@element-plus/icons-vue`
- **路由**：vue-router 5（History 模式 + 全局前置守卫）
- **HTTP**：Axios 封装（统一注入 token、统一解包响应）
- **Markdown 渲染**：marked + DOMPurify（AI 回答转 HTML 前先消毒）

## 📁 项目结构

```
lab-agent/
├── backend/                              # 后端服务（FastAPI）
│   ├── app/
│   │   ├── main.py                       # 应用入口：CORS / 路由 / 异常处理器 / 静态目录 / lifespan
│   │   ├── config.py                     # pydantic-settings 配置（DATABASE_URL / JWT / LLM）
│   │   ├── database.py                   # Engine / SessionLocal / Base / init_db
│   │   ├── api/                          # 接口层（只做参数接收与响应包装）
│   │   │   ├── __init__.py               # 聚合路由，统一挂到 /api
│   │   │   ├── auth.py                   # 登录 / 注册
│   │   │   ├── user.py                   # 个人信息 / 改密 / 用户管理
│   │   │   ├── lab.py                    # 实验室 CRUD
│   │   │   ├── equipment.py              # 设备 CRUD
│   │   │   ├── reservation.py            # 创建 / 列表 / 取消 / 审核
│   │   │   ├── ai.py                     # 对话（普通 + SSE 流式）
│   │   │   ├── conversation.py           # 会话列表 / 消息 / 删除
│   │   │   ├── files.py                  # 文件上传
│   │   │   └── health.py                 # 健康检查（含数据库探活）
│   │   ├── services/                     # 业务层
│   │   │   ├── auth_service.py           # 注册 / 登录 / 密码校验
│   │   │   ├── user_service.py           # 用户管理
│   │   │   ├── lab_service.py            # 实验室分页与 CRUD
│   │   │   ├── equipment_service.py      # 设备分页与 CRUD
│   │   │   ├── reservation_service.py    # 预约校验 / 冲突检测 / 审核 / 超时扫描
│   │   │   ├── conversation_service.py   # 会话与消息落库
│   │   │   ├── agent_service.py          # LangGraph 图构建 + 同步调用 + SSE 事件流
│   │   │   ├── agent_tools.py            # 5 个 LangChain 工具（闭包持有 db / current_user）
│   │   │   └── kb_service.py             # Chroma 向量库：建库 / 检索 / 预热
│   │   ├── models/                       # ORM 模型（6 张表）
│   │   │   ├── user.py                   # users
│   │   │   ├── lab.py                    # labs
│   │   │   ├── equipment.py              # equipments
│   │   │   ├── reservation.py            # reservations
│   │   │   └── conversation.py           # conversations / chat_messages
│   │   ├── schemas/                      # Pydantic 请求 / 响应模型
│   │   ├── dependencies/auth.py          # get_current_user / get_current_admin
│   │   ├── common/
│   │   │   ├── response.py               # Response / PageResponse
│   │   │   └── exceptions.py             # BusinessException + 4 个异常处理器
│   │   └── utils/
│   │       ├── security.py               # 签发 / 解析 token（不叫 jwt.py，避免遮蔽第三方包）
│   │       └── password.py               # bcrypt 哈希与校验
│   ├── data/
│   │   ├── kb/                           # 知识库原文（*.md）
│   │   └── chroma/                       # Chroma 持久化目录（首次启动自动建库）
│   ├── uploads/                          # 上传文件静态目录
│   ├── dev.py                            # 开发启动脚本（端口检查 / 清理孤儿进程）
│   ├── requirements.txt
│   ├── .env                              # 环境变量（本地配置，勿提交到仓库）
│   └── 启动说明.md                        # 后端启动与排错细节
├── frontend/                             # 前端应用（Vue 3 + Vite）
│   ├── src/
│   │   ├── api/                          # 按模块拆分的接口封装
│   │   ├── views/                        # 13 个页面
│   │   │   ├── Home.vue                  # 仪表盘
│   │   │   ├── Lab.vue / LabList.vue     # 实验室管理 / 学生预约入口
│   │   │   ├── Equipment.vue             # 设备管理
│   │   │   ├── LabEquipment.vue          # 实验室设备查看
│   │   │   ├── MyReservation.vue         # 我的预约
│   │   │   ├── AuditReservation.vue      # 预约审核（管理员）
│   │   │   ├── AIChat.vue                # AI 对话（SSE）
│   │   │   ├── User.vue                  # 用户管理（管理员）
│   │   │   ├── Profile.vue / Password.vue
│   │   │   └── Login.vue / Register.vue
│   │   ├── components/ReserveDialog.vue  # 预约弹窗
│   │   ├── layouts/Layout.vue            # 侧边栏 + 顶栏骨架
│   │   ├── router/index.js               # 路由表 + token 守卫
│   │   └── utils/                        # request.js / auth.js / user.js
│   ├── vite.config.js                    # @ 别名 + /api 代理（SSE 关闭缓冲）
│   └── package.json
├── sql/seed_data.sql                     # 演示数据：8 个实验室 + 32 台设备（幂等）
└── README.md
```

## 🚀 快速开始

### 前提条件

- Python 3.10+
- Node.js 22.18+ / 24.12+
- MySQL 8.0+
- 一个兼容 OpenAI 协议的大模型服务（`LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL`）

### 1. 建库

```bash
mysql -uroot -p -e "CREATE DATABASE IF NOT EXISTS lab_agent DEFAULT CHARSET utf8mb4;"
```

> 表结构不用手动建：服务启动时 `init_db()` 会执行 `Base.metadata.create_all`。

### 2. 后端

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 安装依赖
python -m pip install -r requirements.txt
```

在 `backend/.env` 中配置（缺少必填项会在启动时给出明确提示）：

```dotenv
DATABASE_URL=mysql+pymysql://root:你的密码@127.0.0.1:3306/lab_agent
JWT_SECRET_KEY=换成一段随机字符串
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=24

LLM_API_KEY=你的模型密钥
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# 可选，多个用英文逗号分隔
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

启动：

```bash
# 推荐：带端口检查与残留进程清理
python dev.py
python dev.py 8010          # 换端口
python dev.py --kill        # 先清理占用 8000 的残留进程

# 或直接用 uvicorn
python -m uvicorn app.main:app --reload
```

- 接口文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

> 首次启动会加载 Embedding 模型并建向量库（约 8 秒），已放到 lifespan 预热阶段并设 60 秒超时，不会阻塞端口监听。

### 3. 导入演示数据（可选）

```bash
mysql -uroot -p lab_agent < sql/seed_data.sql
```

脚本是幂等的（`ON DUPLICATE KEY UPDATE` / `INSERT IGNORE`），可重复执行；导入后可查到 8 个实验室、32 台设备。

### 4. 前端

```bash
cd frontend
npm install
npm run dev
```

访问 <http://localhost:5173>。Vite 已把 `/api` 代理到 `http://127.0.0.1:8000`，并对 `text/event-stream` 关闭缓冲，SSE 才能逐条到达浏览器。

## 📝 使用指南

### 学生

1. 注册 / 登录（`/register`、`/login`）
2. 进入「实验室列表」，按关键词筛选，查看容量、位置与开放时间
3. 点击「预约」，选择日期与起止时间；可同时指定要预约的设备
4. 在「我的预约」查看状态：待审核 / 已通过 / 已拒绝 / 已取消
5. 待审核状态下可主动取消

### 管理员

1. 「实验室管理」「设备管理」维护基础数据与上下架状态
2. 「预约审核」通过或拒绝待审核记录
3. 「用户管理」维护账号与角色
4. 「AI 对话」中用自然语言提问，例如：
   - 「化学实验室的安全规范是什么？」
   - 「明天下午有哪些实验室有空？」
   - 「帮我约明天 14:00-16:00 的人工智能实验室」

> Agent 在真正落库前会复述「实验室 / 设备、日期、起止时间」并要求确认；未收到「确认」类回复不会调用创建预约工具。

## 🔧 核心实现

### 1. 分层架构与统一响应

```
api（参数接收 / 依赖注入 / 响应包装）
  → services（业务规则 / 事务）
    → models（ORM 映射）
```

- 所有成功响应统一为 `Response.success(data=...)` → `{code: 200, message, data}`
- 业务失败抛 `BusinessException(message, code)`，由 `business_exception_handler` 统一转成 HTTP 200 + 业务 code
- `RequestValidationError` 会把 Pydantic 的字段级报错拼进 message，例如 `请求参数校验错误：body.file: Field required`
- 兜底 `Exception` 处理器只回「服务器内部错误」，堆栈只进日志

### 2. 预约冲突检测

核心判断条件（左闭右开，允许上一场结束时刻等于下一场开始时刻）：

```python
Reservation.lab_id == data.lab_id
Reservation.date == data.date
Reservation.status.in_([0, 1])          # 待审核 + 已通过才算占用
Reservation.start_time < data.end_time  # 时间区间相交
Reservation.end_time > data.start_time
```

- 预约整间实验室时追加 `equipment_id IS NULL`，预约设备时按 `equipment_id` 过滤，两类互不干扰
- 时间统一存 `String("HH:MM")`，保证字典序与时间序一致，可直接用字符串比较与建索引

### 3. 预约状态机

| 状态值 | 含义            | 可执行动作                             |
| ------ | --------------- | -------------------------------------- |
| 0      | 待审核          | 取消、审核通过、审核拒绝、超时自动失效 |
| 1      | 已通过          | —                                      |
| 2      | 已拒绝          | —                                      |
| 3      | 已取消 / 已失效 | —                                      |

`run_expire_scan()` 在 lifespan 中作为 asyncio 任务启动，每 60 秒把「日期已过」或「当天且结束时间已过」的待审核记录置为 3，进程退出时任务被取消。

### 4. LangGraph 对话 Agent

```python
graph = StateGraph(MessagesState)
graph.add_node("agent", agent_node)          # llm.invoke
graph.add_node("tools", ToolNode(tools))     # 执行工具
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", tools_condition)  # 有 tool_call 就进 tools
graph.add_edge("tools", "agent")             # 工具结果回喂模型
graph.compile()
```

- `recursion_limit=10` 限制 agent ⇄ tools 来回轮次，防止模型空转
- 工具通过闭包持有 `db` 与 `current_user`，模型只传业务参数，**不能伪造 user_id**
- 5 个工具：`search_lab_docs` / `list_open_labs` / `list_lab_equipments` / `create_lab_reservation` / `get_today`
- System Prompt 强制：日期问题先调 `get_today`；提交预约前必须复述信息并等待用户确认；不得编造库中不存在的实验室或设备

### 5. RAG 知识库

- 文档来源：`backend/data/kb/*.md`（预约规则、安全规范、开放时间、设备使用）
- 向量库：`chromadb.PersistentClient(path=data/chroma)`，collection 名 `lab_kb`
- Embedding：`BAAI/bge-small-zh-v1.5`，优先只用本地缓存（`local_files_only=True`），没有缓存才联网下载
- 检索：取 top-5，`score = 1 / (1 + distance)`，过滤 `score < 0.5`，按分数排序后只保留前 2 条拼进上下文
- 预热：启动时加载模型 + 跑一次空查询，避免首个用户请求承担约 8 秒的加载开销

### 6. SSE 流式对话

`POST /api/ai/chat/stream` 返回 `text/event-stream`，事件类型：

| type           | 载荷                       | 说明                                                 |
| -------------- | -------------------------- | ---------------------------------------------------- |
| `conversation` | `id`, `title`              | 新会话 ID，前端据此切换当前会话                      |
| `status`       | `message`                  | 阶段提示（如「正在思考…」）                          |
| `tool_start`   | `name`, `label`            | 工具开始，`label` 是中文过程文案                     |
| `tool_end`     | `name`, `label`, `preview` | 工具结束，结果截断到 200 字符做预览                  |
| `token`        | `content`                  | 逐字输出                                             |
| `done`         | —                          | 本轮结束（不再重复带全文）                           |
| `error`        | `message`                  | 流内错误（不抛 HTTP 异常，避免前端拿不到已输出内容） |

实现要点：

- 用 `agent.astream_events(version="v2")` 而不是 `stream_events`：后者在 Pregel 上只实现实验性 v3 协议
- 只接收 `langgraph_node == "agent"` 的 token，过滤内部节点噪声
- 助手回答在流结束后整体落库，而不是每个 token 写一次
- 响应头带 `X-Accel-Buffering: no`，Vite 代理层同样关闭缓冲

### 7. 认证与权限

- 登录成功签发 JWT（payload 含 `user_id`，`JWT_EXPIRE_HOURS` 默认 24 小时）
- `get_current_user`：解析 token → 查库 → 校验用户存在且未被禁用
- `get_current_admin`：在 `get_current_user` 基础上校验 `role == "admin"`，非管理员抛 403
- 前端路由守卫只做体验优化，真正的权限边界在每个接口的 `Depends` 上

## 📄 API 文档

启动后访问 `http://127.0.0.1:8000/docs`。统一前缀 `/api`：

| 模块   | 方法与路径                                                                       | 说明                               |
| ------ | -------------------------------------------------------------------------------- | ---------------------------------- |
| 认证   | `POST /api/auth/login`                                                           | 登录，返回 token                   |
| 认证   | `POST /api/auth/register`                                                        | 注册                               |
| 用户   | `GET /api/user/me` / `PUT /api/user/me`                                          | 当前用户信息                       |
| 用户   | `PUT /api/user/password`                                                         | 修改密码                           |
| 用户   | `GET /api/user/list` / `POST /api/user`                                          | 用户列表 / 新增（管理员）          |
| 用户   | `PUT /api/user/{id}` / `DELETE /api/user/{id}`                                   | 编辑 / 删除（管理员）              |
| 实验室 | `GET /api/lab/list` / `GET /api/lab/{id}`                                        | 分页查询 / 详情                    |
| 实验室 | `POST /api/lab` / `PUT /api/lab/{id}` / `DELETE /api/lab/{id}`                   | 新增 / 编辑 / 删除                 |
| 设备   | `GET /api/equipment/list`                                                        | 按实验室 / 关键词分页              |
| 设备   | `POST /api/equipment` / `PUT /api/equipment/{id}` / `DELETE /api/equipment/{id}` | 增删改                             |
| 预约   | `POST /api/reservation`                                                          | 创建预约（含全部校验）             |
| 预约   | `GET /api/reservation/list`                                                      | 列表（学生只看自己，管理员看全部） |
| 预约   | `PUT /api/reservation/{id}/cancel`                                               | 取消（仅本人 + 待审核）            |
| 预约   | `PUT /api/reservation/{id}/audit`                                                | 审核（管理员，1 通过 / 2 拒绝）    |
| AI     | `POST /api/ai/chat`                                                              | 整包返回对话结果                   |
| AI     | `POST /api/ai/chat/stream`                                                       | SSE 流式对话                       |
| 会话   | `GET /api/ai/conversation/list`                                                  | 会话列表                           |
| 会话   | `GET /api/ai/conversation/{id}/messages`                                         | 历史消息                           |
| 会话   | `DELETE /api/ai/conversation/{id}`                                               | 删除会话                           |
| 文件   | `POST /api/files/upload`                                                         | 上传图片 / 文档（≤100MB）          |
| 系统   | `GET /api/health`                                                                | 服务 + 数据库健康检查              |

## 🩺 常见问题

**端口被占用（winerror 10048）**
Windows 上 `uvicorn --reload` 用 `multiprocessing.spawn` 起子进程，父进程被强杀后子进程会变成孤儿并继续占着 socket，而 `netstat` 显示的是已不存在的父进程 PID。执行 `python dev.py --kill` 一键清理；日常请用 `Ctrl + C` 正常退出。

**`'cryptography' package is required...`**
MySQL 8 默认 `caching_sha2_password`，PyMySQL 在密码缓存未命中时需要 `cryptography`。`requirements.txt` 已包含，若用其他环境安装请确认没有漏装。

**启动卡在 `Waiting for application startup.`**
多半是 Embedding 模型在联网核对 huggingface.co（国内网络常超时并重试 5 次）。代码已优先 `local_files_only=True`，仅本地无缓存时才联网；lifespan 里也加了 60 秒超时兜底。

**前端能打开但所有请求失败**
确认后端端口与 Vite 代理目标一致；CORS 已用正则放行 `localhost / 127.0.0.1` 的任意端口，Vite 端口顺延到 5174 也不会跨域失败。

## 🔮 后续可扩展

1. **自动化测试**：目前没有测试目录，可优先补预约冲突检测（边界：首尾相接、跨天、设备与实验室互斥）与鉴权分支的 pytest 用例。
2. **并发防重**：`create_reservation` 是「先查后插」，高并发下仍可能双写；可加 `SELECT ... FOR UPDATE` 行锁或 `UNIQUE(lab_id, date, slot)` 约束兜底。
3. **部署与可观测**：补 Dockerfile / compose、结构化日志、接口耗时指标与 CI。
4. **RAG 效果评估**：当前只按距离阈值过滤，缺少召回率与答案质量评测集。
5. **分页优化**：深分页仍用 `OFFSET`，数据量上来后可换游标分页。

## 🙏 致谢

- [FastAPI](https://fastapi.tiangolo.com/) · [SQLAlchemy](https://www.sqlalchemy.org/) · [LangGraph](https://langchain-ai.github.io/langgraph/)
- [ChromaDB](https://www.trychroma.com/) · [BAAI/bge-small-zh-v1.5](https://huggingface.co/BAAI/bge-small-zh-v1.5)
- [Vue 3](https://cn.vuejs.org/) · [Element Plus](https://element-plus.org/) · [Vite](https://vite.dev/)
