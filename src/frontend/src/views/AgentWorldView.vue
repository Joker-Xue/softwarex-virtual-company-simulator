<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAgentWorldStore } from '@/stores/agentWorld'
import type { CompanyRoom } from '@/stores/agentWorld'
import OfficeCanvas from '@/components/agent/OfficeCanvas.vue'
import AgentPanel from '@/components/agent/AgentPanel.vue'
import PromotionModal from '@/components/agent/PromotionModal.vue'
import RoomInterior from '@/components/agent/RoomInterior.vue'
import request from '@/utils/request'

const router = useRouter()
const store = useAgentWorldStore()
const loading = ref(true)
const promotionData = ref<{ level: number; title: string } | null>(null)
const activeRoom = ref<CompanyRoom | null>(null)
const showRoomInterior = ref(false)
const simSpeed = ref(1)

onMounted(async () => {
  try {
    const profile = await store.fetchProfile()
    if (!profile) {
      loading.value = false
      router.replace('/agent-setup')
      return
    }
    await store.fetchOnlineAgents()
    store.connectWS()
    await Promise.all([store.fetchTasks(), store.fetchFriends(), store.fetchUnread(), store.fetchMap()])
  } catch (e) {
    console.error('AgentWorld init error:', e)
    router.replace('/agent-setup')
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  store.disconnectWS()
})

function onPromotion(data: { level: number; title: string }) {
  promotionData.value = data
}

function onEnterRoom(roomConfig: any) {
  const ROOM_NAME_ALIASES: Record<string, string[]> = {
    'Meeting Room': ['Meeting RoomA'],
  }
  // roomConfig is from the static ROOMS array (companyMap.ts).
  // Try to find the matching API room (with interior_objects) by name.
  const candidateNames = [roomConfig.name, ...(ROOM_NAME_ALIASES[roomConfig.name] || [])]
  const apiRoom = store.roomMap.find(r =>
    candidateNames.includes(r.name) ||
    (r.room_type === roomConfig.type && r.floor === roomConfig.floor),
  )
  if (apiRoom) {
    activeRoom.value = apiRoom
  } else {
    // Fallback: construct a CompanyRoom from the static config with empty interior
    activeRoom.value = {
      id: roomConfig.id,
      name: roomConfig.name,
      room_type: roomConfig.type,
      department: roomConfig.department,
      x: roomConfig.x,
      y: roomConfig.y,
      width: roomConfig.width,
      height: roomConfig.height,
      capacity: 0,
      floor: roomConfig.floor ?? 1,
      interior_objects: [],
      description: null,
    }
  }
  showRoomInterior.value = true
}

function onCloseRoomInterior() {
  showRoomInterior.value = false
  activeRoom.value = null
}

async function setSimSpeed(speed: number) {
  simSpeed.value = speed
  try {
    await request.post('/api/simulation/speed?multiplier=' + speed)
  } catch { /* ignore */ }
}
</script>

<template>
  <div class="agent-world" v-loading="loading">
    <template v-if="!loading && store.hasProfile">
      <div class="world-layout">
        <div class="canvas-area">
          <div class="canvas-header">
            <h3>🏢 virtual company</h3>
            <div class="header-controls">
              <div class="speed-controls">
                <span class="speed-label">SimulateSpeed</span>
                <button v-for="s in [1, 2, 5]" :key="s" class="speed-btn" :class="{ active: simSpeed === s }" @click="setSimSpeed(s)">{{ s }}x</button>
              </div>
              <span class="ws-status" :class="{ online: store.wsConnected }">
                {{ store.wsConnected ? '● Connected' : '○ Not connected' }}
              </span>
            </div>
          </div>
          <OfficeCanvas @enter-room="onEnterRoom" />
        </div>
        <div class="panel-area">
          <AgentPanel @promotion="onPromotion" />
        </div>
      </div>
    </template>
    <PromotionModal v-if="promotionData" :level="promotionData.level" :title="promotionData.title" @close="promotionData = null" />
    <RoomInterior
      :room="activeRoom"
      :agents="store.onlineAgents"
      :visible="showRoomInterior"
      @close="onCloseRoomInterior"
    />
  </div>
</template>

<style scoped>
.agent-world {
  height: 100vh;
  overflow: hidden;
  background: var(--bg-deep);
  background-image:
    linear-gradient(rgba(34, 211, 238, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(34, 211, 238, 0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  color: var(--text-primary);
}
.world-layout {
  display: flex;
  height: 100%;
  gap: 0;
  overflow: hidden;
}

/* ── Canvas Area with neon frame ── */
.canvas-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 16px;
  position: relative;
  overflow: hidden;
}
.canvas-area::before,
.canvas-area::after {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  border-style: solid;
  border-color: var(--accent-cyan);
  pointer-events: none;
  z-index: 2;
}
.canvas-area::before {
  top: 8px;
  left: 8px;
  border-width: 2px 0 0 2px;
}
.canvas-area::after {
  bottom: 8px;
  right: 8px;
  border-width: 0 2px 2px 0;
}

/* ── Header bar ── */
.canvas-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-dim);
}
.canvas-header h3 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--accent-cyan);
  text-shadow: 0 0 8px rgba(34, 211, 238, 0.4);
}
.header-controls {
  display: flex;
  align-items: center;
  gap: 14px;
}
.speed-controls {
  display: flex;
  align-items: center;
  gap: 4px;
}
.speed-label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  margin-right: 4px;
}
.speed-btn {
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid var(--border-dim);
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}
.speed-btn:hover {
  border-color: rgba(34, 211, 238, 0.3);
  color: var(--text-primary);
}
.speed-btn.active {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
  background: rgba(34, 211, 238, 0.1);
  box-shadow: 0 0 6px rgba(34, 211, 238, 0.2);
}

/* ── WebSocket status indicator ── */
.ws-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--accent-rose);
  letter-spacing: 0.5px;
}
.ws-status::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent-rose);
  box-shadow: 0 0 6px var(--accent-rose);
  animation: cyber-pulse 2s ease-in-out infinite;
}
.ws-status.online {
  color: var(--accent-emerald);
}
.ws-status.online::before {
  background: var(--accent-emerald);
  box-shadow: 0 0 6px var(--accent-emerald);
}

/* ── Glowing vertical divider ── */
.panel-area {
  width: 360px;
  flex-shrink: 0;
  position: relative;
  background: var(--bg-card);
  backdrop-filter: blur(16px) saturate(1.3);
  -webkit-backdrop-filter: blur(16px) saturate(1.3);
  border-left: 1px solid var(--border-glow);
  box-shadow: -4px 0 20px rgba(34, 211, 238, 0.06);
  overflow-y: auto;
}
.panel-area::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 1px;
  height: 100%;
  background: linear-gradient(
    180deg,
    transparent 0%,
    var(--accent-cyan) 20%,
    var(--accent-violet) 50%,
    var(--accent-cyan) 80%,
    transparent 100%
  );
  opacity: 0.4;
  pointer-events: none;
  z-index: 1;
}

/* ── Custom scrollbar ── */
.panel-area::-webkit-scrollbar {
  width: 4px;
}
.panel-area::-webkit-scrollbar-track {
  background: transparent;
}
.panel-area::-webkit-scrollbar-thumb {
  background: rgba(34, 211, 238, 0.15);
  border-radius: 2px;
}
.panel-area::-webkit-scrollbar-thumb:hover {
  background: rgba(34, 211, 238, 0.3);
}

@keyframes cyber-pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 4px currentColor; }
  50% { opacity: 0.5; box-shadow: 0 0 12px currentColor; }
}
</style>
