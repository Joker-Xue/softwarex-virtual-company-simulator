import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/agent-world',
    },
    {
      path: '/agent-setup',
      name: 'agentSetup',
      component: () => import('@/views/AgentProfileSetup.vue'),
    },
    {
      path: '/agent-world',
      name: 'agentWorld',
      component: () => import('@/views/AgentWorldView.vue'),
    },
  ],
})

export default router
