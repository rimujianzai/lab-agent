<template>
  <div>
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <div style="font-size: 16px; font-weight: bold">
            AI智能助手
          </div>
          <el-button type="primary" :icon="Plus" @click="handleNewChat">新对话</el-button>
        </div>
      </template>

      <div style="display: flex; gap: 12px; align-items: flex-start">
        <!-- 左侧：历史对话 -->
        <div
          style="
            width: 220px;
            flex: none;
            border-right: 1px solid #ebeef5;
            padding-right: 10px;
          "
        >
          <div style="font-size: 13px; color: #909399; margin-bottom: 8px">历史对话</div>
          <div v-loading="historyLoading" style="height: 480px; overflow-y: auto">
            <div
              v-if="!conversations.length"
              style="font-size: 13px; color: #c0c4cc; text-align: center; padding-top: 20px"
            >
              暂无历史对话
            </div>
            <div
              v-for="item in conversations"
              :key="item.id"
              :style="{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                padding: '8px',
                marginBottom: '6px',
                borderRadius: '6px',
                cursor: 'pointer',
                backgroundColor: item.id === conversationId ? '#ecf5ff' : '#f7f8fa'
              }"
              @click="handleOpenConversation(item)"
            >
              <div style="flex: 1; min-width: 0">
                <div
                  :style="{
                    fontSize: '13px',
                    color: item.id === conversationId ? '#409eff' : '#333',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }"
                >
                  {{ item.title }}
                </div>
                <div style="font-size: 12px; color: #909399">
                  {{ formatTime(item.create_time) }}
                </div>
              </div>
              <el-button
                type="danger"
                text
                :icon="Delete"
                @click.stop="handleDeleteConversation(item)"
              />
            </div>

            <div v-if="total > params.pageSize" style="margin-top: 8px; text-align: center">
              <el-pagination
                v-model:current-page="params.page"
                :page-size="params.pageSize"
                :total="total"
                small
                background
                layout="prev, pager, next"
                @current-change="loadConversations"
              />
            </div>
          </div>
        </div>

        <!-- 右侧：对话区 -->
        <div style="flex: 1; min-width: 0">
          <div
            ref="listRef"
            v-loading="openLoading"
            style="
              height: 480px;
              overflow-y: auto;
              padding: 8px 4px;
              background-color: #fafafa;
              border-radius: 6px;
            "
          >
            <div
              v-for="(item, index) in messages"
              :key="index"
              :style="{
                display: 'flex',
                justifyContent: item.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: '12px'
              }"
            >
              <div
                :style="{
                  maxWidth: '70%',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  backgroundColor: item.role === 'user' ? '#409eff' : '#fff',
                  color: item.role === 'user' ? '#fff' : '#333',
                  lineHeight: '1.6',
                  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.06)'
                }"
              >
                <div
                  v-if="item.role === 'assistant' && item.status"
                  style="margin-bottom: 6px; font-size: 12px; color: #909399"
                >
                  {{ item.status }}
                </div>

                <div
                  v-if="item.role === 'assistant' && item.steps?.length"
                  style="margin-bottom: 8px; font-size: 12px; color: #909399; line-height: 1.5"
                >
                  <div v-for="(step, i) in item.steps" :key="i">· {{ step }}</div>
                </div>
                <div v-html="parseMarkdown(item.content)"></div>
              </div>
            </div>
          </div>

          <div style="margin-top: 12px; display: flex; gap: 8px; align-items: flex-end">
            <el-input
              v-model="input"
              type="textarea"
              :rows="2"
              placeholder="问问实验室怎么预约、开放时间..."
              @keydown.enter.exact.prevent="handleSend"
              @keydown.enter.shift.stop
            ></el-input>
            <el-button type="primary" @click="handleSend" :loading="loading">发送</el-button>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify' // 过滤危险的 HTML，防止 XSS 攻击
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import {
  chatStreamApi,
  getConversationPageList,
  getConversationMessages,
  deleteConversationApi
} from '@/api/ai'

// 开场白只是界面引导，不落库、也不发给后端（见 handleSend 里截掉它）
const GREETING =
  '你好，我是实验室预约助手。可以问规则和开放实验室，也可以说「帮我预约明天下午的实验室」，确认后我会帮你提交。'

const messages = ref([{ role: 'assistant', content: GREETING }])
const input = ref('')
const loading = ref(false)
const openLoading = ref(false)
const listRef = ref()

// 当前会话 id。null 表示这是一轮全新对话，后端会在第一条消息落地时建会话，
// 再把 id 通过 SSE 的 conversation 事件回给前端
const conversationId = ref(null)
const conversations = ref([])
const historyLoading = ref(false)
const total = ref(0)
const params = reactive({ page: 1, pageSize: 20 })

const scrollToBottom = () => {
  nextTick(() => {
    const elem = listRef.value
    if (elem) elem.scrollTop = elem.scrollHeight
  })
}

// 后端给的是 ISO 8601（带 T），列表里只需要到分钟
const formatTime = (text) => {
  if (!text) return ''
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return text
  const pad = (num) => String(num).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

// 加载历史会话列表
const loadConversations = async () => {
  historyLoading.value = true
  try {
    const res = await getConversationPageList({
      page: params.page,
      page_size: params.pageSize
    })
    if (res.code === 200) {
      const list = res.data?.list || []
      // 删到当前页空了就自动退回上一页，否则会停在一个永远空白的列表上
      if (!list.length && params.page > 1) {
        params.page -= 1
        return loadConversations()
      }
      conversations.value = list
      total.value = res.data?.total || 0
    }
  } finally {
    historyLoading.value = false
  }
}

// 新对话：只是把界面清空，不发请求。会话等真正提问时才由后端创建，
// 这样历史列表里不会堆一堆空会话
const handleNewChat = () => {
  if (loading.value) return
  conversationId.value = null
  messages.value = [{ role: 'assistant', content: GREETING }]
  input.value = ''
  scrollToBottom()
}

// 打开某个历史会话
const handleOpenConversation = async (item) => {
  if (loading.value || item.id === conversationId.value) return
  openLoading.value = true
  try {
    const res = await getConversationMessages(item.id)
    if (res.code === 200) {
      conversationId.value = item.id
      // 直接整体替换：后端只在有消息时才建会话，不会加载出空对话
      messages.value = res.data || []
      scrollToBottom()
    }
  } finally {
    openLoading.value = false
  }
}

// 删除某个历史会话
const handleDeleteConversation = (item) => {
  ElMessageBox.confirm(`确认删除对话 [${item.title}] ？`, '确认删除', {
    type: 'warning'
  }).then(async () => {
    const res = await deleteConversationApi(item.id)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      // 删的正好是当前打开的会话：退回新对话，
      // 否则会继续拿着一个已经被删掉的 conversation_id 发消息
      if (item.id === conversationId.value) {
        conversationId.value = null
        messages.value = [{ role: 'assistant', content: GREETING }]
      }
      loadConversations()
    }
  })
}

const handleSend = async () => {
  const text = input.value.trim()
  if (!text || loading.value) return
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true
  scrollToBottom()
  // 必须用 reactive：普通对象 push 后再改字段，视图可能不更新
  const assistant = reactive({
    role: 'assistant',
    content: '', // 正文：靠 token 一点点拼
    status: '正在思考…', // 当前状态文案
    steps: [] // 过程流水，不进下次 history
  })
  messages.value.push(assistant)
  // 开场白是界面引导，发请求前把它截掉；从第一条用户消息开始算历史。
  // 末尾的 -1 去掉刚插入的那个空助手（content 还是空串）
  const firstUser = messages.value.findIndex((item) => item.role === 'user')
  const history = messages.value
    .slice(firstUser, -1)
    .filter((item) => item.role === 'user' || item.role === 'assistant')
    // 只保留 role/content；status、steps 丢掉
    .map(({ role, content }) => ({ role, content }))
  try {
    // 第二个参数是回调：每解析出一条 SSE 事件就进一次
    await chatStreamApi(
      { messages: history, conversation_id: conversationId.value },
      (evt) => {
        if (evt.type === 'conversation') {
          // 后端刚把会话建出来，记下 id 才能接着往下聊
          if (!conversationId.value) {
            conversationId.value = evt.id
            loadConversations()
          }
        } else if (evt.type === 'status') {
          assistant.status = evt.message || '正在思考…'
        } else if (evt.type === 'tool_start') {
          const label = evt.label || evt.name || '工具'
          assistant.status = `正在${label}…`
          assistant.steps.push(`开始：${label}`)
        } else if (evt.type === 'tool_end') {
          const label = evt.label || evt.name || '工具'
          assistant.status = `${label}完成`
          assistant.steps.push(`完成：${label}`)
        } else if (evt.type === 'token') {
          assistant.content += evt.content || '' // 打字机：追加，不是覆盖
          assistant.status = '' // 开始出字后清掉「正在…」，避免叠在一起
        } else if (evt.type === 'done') {
          assistant.status = ''
          // 注意：不要在这里再 append 一整段正文，否则会双份
        } else if (evt.type === 'error') {
          assistant.status = ''
          if (!assistant.content) {
            assistant.content = evt.message || '请求失败'
          }
          ElMessage.error(evt.message || '请求失败')
        }
        scrollToBottom()
      }
    )
  } catch (err) {
    assistant.status = ''
    if (!assistant.content) {
      assistant.content = err.message || '网络异常'
    }
    ElMessage.error(err.message || '网络异常')
  } finally {
    loading.value = false
    assistant.status = ''
    scrollToBottom()
  }
}

// 将 markdown 字符串转换为安全的 HTML 字符串
const parseMarkdown = (text) => {
  if (!text) return ''
  marked.setOptions({ breaks: true }) // 把 \n 转换成 <br>
  // 使用 marked 解析，然后用 DOMPurify 清理
  const rawHtml = marked.parse(text)
  return DOMPurify.sanitize(rawHtml)
}

onMounted(() => {
  loadConversations()
})
</script>
