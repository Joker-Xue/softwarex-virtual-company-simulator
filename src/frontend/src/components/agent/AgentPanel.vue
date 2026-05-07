<script setup lang="ts">
import { ref, watch } from 'vue'
import { useAgentWorldStore } from '@/stores/agentWorld'
import TaskList from './TaskList.vue'
import FriendList from './FriendList.vue'
import ChatWindow from './ChatWindow.vue'
import ProfileCard from './ProfileCard.vue'
import EventBoard from './EventBoard.vue'
import AnalyticsDashboard from './AnalyticsDashboard.vue'
import PersonalityTrace from './PersonalityTrace.vue'

const emit = defineEmits<{
  promotion: [data: { level: number; title: string }]
  'enter-room': [room: any]
}>()
const store = useAgentWorldStore()
const activeTab = ref('profile')

watch(() => store.selectedAgent, (agent) => {
  if (agent) activeTab.value = 'profile'
})
</script>

<template>
  <div class="agent-panel">
    <div class="panel-tabs">
      <button :class="{ active: activeTab === 'profile' }" @click="activeTab = 'profile'">
        Role
      </button>
      <button :class="{ active: activeTab === 'tasks' }" @click="activeTab = 'tasks'">
        Task
      </button>
      <button :class="{ active: activeTab === 'friends' }" @click="activeTab = 'friends'">
        friend
        <span v-if="store.pendingRequests.length" class="badge">
          <span class="pulse-dot pulse-dot-rose"></span>
          {{ store.pendingRequests.length }}
        </span>
      </button>
      <button :class="{ active: activeTab === 'chat' }" @click="activeTab = 'chat'">
        chat
        <span v-if="store.unreadCount" class="badge">
          <span class="pulse-dot pulse-dot-rose"></span>
          {{ store.unreadCount }}
        </span>
      </button>
      <button :class="{ active: activeTab === 'events' }" @click="activeTab = 'events'">
        Activity
      </button>
      <button :class="{ active: activeTab === 'analytics' }" @click="activeTab = 'analytics'">
        data
      </button>
      <button class="tab-btn" :class="{ active: activeTab === 'trace' }" @click="activeTab = 'trace'">
        <span>🧬</span> trace
      </button>
    </div>

    <div class="panel-content cyber-scroll">
      <Transition name="fade" mode="out-in">
        <ProfileCard v-if="activeTab === 'profile'" key="profile" @open-chat="(id) => { store.fetchMessages(id); activeTab = 'chat' }" />
        <TaskList v-else-if="activeTab === 'tasks'" key="tasks" @promotion="(d) => emit('promotion', d)" />
        <FriendList v-else-if="activeTab === 'friends'" key="friends" @open-chat="(id) => { store.fetchMessages(id); activeTab = 'chat' }" />
        <ChatWindow v-else-if="activeTab === 'chat'" key="chat" />
        <EventBoard v-else-if="activeTab === 'events'" key="events" />
        <AnalyticsDashboard v-else-if="activeTab === 'analytics'" key="analytics" />
        <PersonalityTrace v-else-if="activeTab === 'trace'" key="trace" />
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.agent-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-surface);
  border-left: 2px solid rgba(34, 211, 238, 0.15);
  box-shadow: -4px 0 20px rgba(34, 211, 238, 0.03);
}
.panel-tabs {
  display: flex;
  border-bottom: 1px solid var(--border-dim);
  flex-shrink: 0;
  background: var(--bg-deep);
}
.panel-tabs button {
  flex: 1;
  padding: 12px 4px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 15px;
  font-family: var(--font-body);
  color: var(--text-muted);
  position: relative;
  transition: all var(--duration-base) ease;
}
.panel-tabs button:hover {
  color: var(--accent-cyan);
  background: rgba(34, 211, 238, 0.05);
}
.panel-tabs button.active {
  color: var(--accent-cyan);
  font-weight: 600;
  background: rgba(34, 211, 238, 0.08);
  text-shadow: 0 0 8px rgba(34, 211, 238, 0.4);
}
.panel-tabs button.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 10%;
  right: 10%;
  height: 2px;
  background: var(--accent-cyan);
  box-shadow: 0 0 8px rgba(34, 211, 238, 0.6);
  border-radius: 2px 2px 0 0;
}
.badge {
  position: absolute;
  top: 4px;
  right: 4px;
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-rose);
  background: rgba(251, 113, 133, 0.12);
  padding: 1px 6px;
  border-radius: 8px;
  border: 1px solid rgba(251, 113, 133, 0.25);
}
.badge .pulse-dot {
  width: 6px;
  height: 6px;
}
.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

/* Transition */
.fade-enter-active {
  transition: opacity 0.25s var(--ease-out-expo), transform 0.25s var(--ease-out-expo);
}
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.fade-leave-to {
  opacity: 0;
}
</style>
