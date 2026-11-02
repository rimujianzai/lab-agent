import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import ElementPlus from 'element-plus'
// Element Plus 默认 locale 是英文：不配这个，分页的 total 会显示 "Total"、
// 跳页框会显示 "Go to"、表格空状态是 "No Data"，中文项目里很突兀。
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import '@/assets/global.css'

const app = createApp(App)
app.use(router)
app.use(ElementPlus, { locale: zhCn })
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')
