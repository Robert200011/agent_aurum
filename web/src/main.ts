import 'ant-design-vue/dist/reset.css'
import 'dayjs/locale/zh-cn'
import '@/styles/main.css'

import { createApp } from 'vue'
import dayjs from 'dayjs'

import App from '@/App.vue'
import router from '@/router'
import { pinia } from '@/stores'

dayjs.locale('zh-cn')

createApp(App).use(pinia).use(router).mount('#app')
