import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/agent-world' },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginRegister.vue'),
      meta: { guest: true },
    },
    {
      path: '/agent-setup',
      name: 'agentSetup',
      component: () => import('@/views/AgentProfileSetup.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/agent-world',
      name: 'agentWorld',
      component: () => import('@/views/AgentWorldView.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) next({ name: 'login' })
  else if (to.meta.guest && token) next({ name: 'agentWorld' })
  else next()
})

export default router
