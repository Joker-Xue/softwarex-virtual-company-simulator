import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import Particles from '@tsparticles/vue3'
import { loadSlim } from '@tsparticles/slim'
import { MotionPlugin } from '@vueuse/motion'

import App from './App.vue'
import router from './router'
import './assets/main.css'
import './styles/cyber-theme.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.use(Particles, {
  init: async (engine) => {
    await loadSlim(engine)
  },
})
app.use(MotionPlugin)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')
