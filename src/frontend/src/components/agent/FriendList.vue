<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import { useAgentWorldStore } from '@/stores/agentWorld'
import { CAREER_LEVELS, AVATAR_COLORS } from '@/constants/companyMap'

const emit = defineEmits<{ openChat: [agentId: number] }>()
const store = useAgentWorldStore()

const activeView = ref<'friends' | 'requests'>('friends')

onMounted(() => {
  store.fetchFriends()
  store.fetchPendingRequests()
})

watch(() => store.friendAcceptedNotif, (notif) => {
  if (notif) {
    ElNotification({
      title: 'Friend application has been approved',
      message: `${notif.nickname} Passed your friend application`,
      type: 'success',
      duration: 4000,
      position: 'top-right',
    })
  }
})

function switchToRequests() {
  activeView.value = 'requests'
  store.fetchSentRequests()
  store.fetchReceivedHistory()
}

async function accept(id: number) {
  try {
    await store.acceptFriend(id)
    ElMessage.success('Accepted')
    store.fetchReceivedHistory()
  } catch { ElMessage.error('Operation failed') }
}

async function reject(id: number) {
  try {
    await store.rejectFriend(id)
    ElMessage.success('Rejected')
    store.fetchReceivedHistory()
  } catch { ElMessage.error('Operation failed') }
}

function compatColor(label: string): string {
  if (label === 'excellent') return '#22c55e'
  if (label === 'good') return '#eab308'
  if (label === 'generally') return '#f97316'
  return '#ef4444'
}

function roleLabel(role: string): string {
  if (role === 'mentor') return 'tutor'
  if (role === 'mentee') return 'student'
  return ''
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m} min ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} h ago`
  return `${Math.floor(h / 24)} d ago`
}

const STATUS_TEXT: Record<string, string> = {
  pending: 'Waiting to pass',
  accepted: 'Passed',
  rejected: 'Rejected',
}
</script>

<template>
  <div class="friend-list">
    <!-- Top navigation -->
    <div class="top-nav">
      <button class="nav-btn" :class="{ active: activeView === 'friends' }" @click="activeView = 'friends'">
        Friend List
        <span v-if="store.friends.length" class="count-badge">{{ store.friends.length }}</span>
      </button>
      <button class="nav-btn" :class="{ active: activeView === 'requests' }" @click="switchToRequests">
        Application record
        <span v-if="store.pendingRequests.length" class="count-badge dot-badge">
          <span class="pulse-dot pulse-dot-rose"></span>{{ store.pendingRequests.length }}
        </span>
      </button>
    </div>

    <!-- ── Friend List view  -->
    <template v-if="activeView === 'friends'">
      <!-- Pendingask（received） -->
      <div v-if="store.pendingRequests.length" class="section">
        <div class="section-title">Pendingask ({{ store.pendingRequests.length }})</div>
        <div v-for="req in store.pendingRequests" :key="req.id" class="friend-item pending">
          <div class="friend-avatar" :style="{ background: AVATAR_COLORS[req.avatar_key] || '#6366f1', boxShadow: '0 0 10px ' + (AVATAR_COLORS[req.avatar_key] || '#6366f1') }">
            {{ req.nickname?.[0] || '?' }}
          </div>
          <div class="friend-info">
            <div class="friend-name">{{ req.nickname }}</div>
            <div class="req-time">{{ timeAgo(req.created_at) }}</div>
          </div>
          <button class="cyber-btn cyber-btn-sm cyber-btn-emerald" @click.stop="accept(req.id)">accept</button>
          <button class="cyber-btn cyber-btn-sm cyber-btn-rose" @click.stop="reject(req.id)">reject</button>
        </div>
      </div>

      <!-- Friend List -->
      <div class="section">
        <div class="section-title">friend ({{ store.friends.length }})</div>
        <div v-if="store.friends.length === 0" class="empty">No friends yet，Click on other roles on the map to add them</div>
        <div
          v-for="f in store.friends" :key="f.id"
          class="friend-item"
          @click="emit('openChat', f.from_id === store.myProfile?.id ? f.to_id : f.from_id)"
        >
          <div class="friend-avatar" :style="{ background: AVATAR_COLORS[f.friend_avatar] || '#6366f1', boxShadow: '0 0 10px ' + (AVATAR_COLORS[f.friend_avatar] || '#6366f1') }">
            {{ f.friend_nickname?.[0] || '?' }}
          </div>
          <div class="friend-info">
            <div class="friend-name-row">
              <span class="friend-name">{{ f.friend_nickname }}</span>
              <span v-if="f.role" class="cyber-badge" :class="f.role === 'mentor' ? 'cyber-badge-violet' : 'cyber-badge-amber'">
                {{ roleLabel(f.role) }}
              </span>
            </div>
            <div class="friend-level">{{ CAREER_LEVELS[f.friend_level]?.title || 'Intern' }}</div>
            <div class="affinity-row">
              <span class="affinity-label">affinity</span>
              <div class="affinity-track">
                <div class="affinity-fill" :style="{ width: (f.affinity ?? 50) + '%' }"></div>
              </div>
              <span class="affinity-val">{{ f.affinity ?? 50 }}</span>
            </div>
          </div>
          <div class="friend-actions">
            <el-tooltip v-if="f.compatibility_label" :content="`compatible: ${(f.compatibility_score * 100).toFixed(0)}% (${f.friend_mbti})`" placement="top">
              <span class="cyber-badge cyber-badge-cyan compat-tag">{{ f.compatibility_label }}</span>
            </el-tooltip>
            <button class="cyber-btn cyber-btn-sm">chat</button>
          </div>
        </div>
      </div>
    </template>

    <!-- ── Application record view  -->
    <template v-else>
      <!-- sent requests -->
      <div class="section">
        <div class="section-title">sent requests ({{ store.sentRequests.length }})</div>
        <div v-if="store.sentRequests.length === 0" class="empty">No applications have been issued yet</div>
        <div v-for="req in store.sentRequests" :key="req.id" class="req-item">
          <div class="friend-avatar" :style="{ background: AVATAR_COLORS[req.avatar_key] || '#6366f1', boxShadow: '0 0 8px ' + (AVATAR_COLORS[req.avatar_key] || '#6366f1') }">
            {{ req.nickname?.[0] || '?' }}
          </div>
          <div class="req-info">
            <div class="req-name">{{ req.nickname }}</div>
            <div class="req-time">{{ timeAgo(req.created_at) }}</div>
          </div>
          <div class="req-status" :class="`status-${req.status}`">
            <span v-if="req.status === 'pending'" class="pulse-dot pulse-dot-amber" style="display:inline-block;margin-right:4px"></span>
            <span v-else-if="req.status === 'accepted'">✓ </span>
            <span v-else>✕ </span>
            {{ STATUS_TEXT[req.status] || req.status }}
          </div>
        </div>
      </div>

      <!-- received requests -->
      <div class="section">
        <div class="section-title">received requests ({{ store.receivedHistory.length }})</div>
        <div v-if="store.receivedHistory.length === 0" class="empty">received requests</div>
        <div v-for="req in store.receivedHistory" :key="req.id" class="req-item">
          <div class="friend-avatar" :style="{ background: AVATAR_COLORS[req.avatar_key] || '#6366f1', boxShadow: '0 0 8px ' + (AVATAR_COLORS[req.avatar_key] || '#6366f1') }">
            {{ req.nickname?.[0] || '?' }}
          </div>
          <div class="req-info">
            <div class="req-name">{{ req.nickname }}</div>
            <div class="req-time">{{ timeAgo(req.created_at) }}</div>
          </div>
          <!-- Pending：Show accept/reject -->
          <template v-if="req.status === 'pending'">
            <button class="cyber-btn cyber-btn-sm cyber-btn-emerald" @click="accept(req.id)">accept</button>
            <button class="cyber-btn cyber-btn-sm cyber-btn-rose" @click="reject(req.id)">reject</button>
          </template>
          <!-- Processed：show��Status -->
          <div v-else class="req-status" :class="`status-${req.status}`">
            <span v-if="req.status === 'accepted'">✓ </span>
            <span v-else>✕ </span>
            {{ STATUS_TEXT[req.status] || req.status }}
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.friend-list {
  display: flex; flex-direction: column; gap: 14px;
  font-family: var(--font-body);
}

/* ── Top Nav ── */
.top-nav {
  display: flex; gap: 4px;
  background: var(--bg-deep); border-radius: var(--radius-md);
  padding: 4px; border: 1px solid var(--border-dim);
}
.nav-btn {
  flex: 1; padding: 7px 12px; border: none; cursor: pointer;
  font-size: 15px; font-family: var(--font-body);
  border-radius: calc(var(--radius-md) - 2px);
  color: var(--text-muted); background: transparent;
  display: flex; align-items: center; justify-content: center; gap: 5px;
  min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: all var(--duration-base);
}
.nav-btn:hover { color: var(--accent-cyan); background: rgba(34,211,238,0.05); }
.nav-btn.active {
  color: var(--accent-cyan); font-weight: 600;
  background: rgba(34,211,238,0.1);
  text-shadow: 0 0 8px rgba(34,211,238,0.4);
}
.count-badge {
  font-size: 12px; font-weight: 700; padding: 1px 5px;
  border-radius: 8px; background: rgba(34,211,238,0.15);
  color: var(--accent-cyan); font-family: var(--font-mono);
  flex-shrink: 0;
}
.dot-badge {
  background: rgba(251,113,133,0.12); color: var(--accent-rose);
  display: flex; align-items: center; gap: 3px;
}

/* ── Section ── */
.section-title {
  font-family: var(--font-display); font-weight: 700; font-size: 14px;
  margin-bottom: 8px; color: var(--accent-amber); letter-spacing: 1px;
  text-shadow: 0 0 8px rgba(251,191,36,0.3); text-transform: uppercase;
}
.empty { text-align: center; color: var(--text-muted); padding: 18px 0; font-size: 14px; }

/* ── Friend Item ── */
.friend-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: var(--radius-md); cursor: pointer;
  background: var(--bg-surface); border: 1px solid var(--border-dim);
  transition: border-color var(--duration-base), background var(--duration-base);
}
.friend-item:hover { border-color: var(--border-glow); background: var(--bg-hover); }
.friend-item.pending { background: rgba(251,191,36,0.04); border-color: rgba(251,191,36,0.15); }

/* ── Request Item (Application record) ── */
.req-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: var(--radius-md);
  background: var(--bg-surface); border: 1px solid var(--border-dim);
  margin-bottom: 6px;
}
.req-info { flex: 1; min-width: 0; }
.req-name { font-weight: 600; font-size: 15px; color: var(--text-primary); }
.req-time { font-size: 13px; color: var(--text-muted); font-family: var(--font-mono); margin-top: 2px; }

/* Status badges */
.req-status {
  font-size: 14px; font-weight: 600; white-space: nowrap;
  display: flex; align-items: center;
  padding: 2px 8px; border-radius: 10px; border: 1px solid;
  max-width: 128px; overflow: hidden; text-overflow: ellipsis;
}
.status-pending {
  color: var(--accent-amber); border-color: rgba(251,191,36,0.3);
  background: rgba(251,191,36,0.08);
}
.status-accepted {
  color: #22c55e; border-color: rgba(34,197,94,0.3);
  background: rgba(34,197,94,0.08);
}
.status-rejected {
  color: var(--accent-rose); border-color: rgba(251,113,133,0.3);
  background: rgba(251,113,133,0.08);
}

/* ── Shared avatar ── */
.friend-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 700; font-size: 16px; flex-shrink: 0;
  border: 1.5px solid rgba(255,255,255,0.15);
}
.friend-info { flex: 1; min-width: 0; }
.friend-name-row { display: flex; align-items: center; gap: 6px; min-width: 0; }
.friend-name { font-weight: 600; font-size: 16px; color: var(--text-primary); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.friend-level { font-size: 13px; color: var(--accent-violet); font-family: var(--font-mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.affinity-row { display: flex; align-items: center; gap: 6px; margin-top: 4px; }
.affinity-label { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.affinity-track { flex: 1; max-width: 120px; height: 6px; background: rgba(34,211,238,0.08); border-radius: 3px; overflow: hidden; }
.affinity-fill {
  height: 100%; border-radius: 3px;
  background: linear-gradient(90deg, var(--accent-rose), var(--accent-amber), var(--accent-emerald));
  box-shadow: 0 0 6px rgba(52,211,153,0.25); transition: width 0.6s var(--ease-out-expo);
}
.affinity-val { font-size: 12px; color: var(--text-muted); font-family: var(--font-mono); min-width: 20px; text-align: right; }
.friend-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; max-width: 96px; }
.compat-tag { font-size: 13px; cursor: default; max-width: 100%; }

/* Color variants */
.cyber-btn-emerald { border-color: var(--accent-emerald); color: var(--accent-emerald); text-shadow: 0 0 6px rgba(52,211,153,0.3); }
.cyber-btn-emerald:hover { background: rgba(52,211,153,0.1); box-shadow: 0 0 15px rgba(52,211,153,0.2); }
.cyber-btn-rose { border-color: var(--accent-rose); color: var(--accent-rose); text-shadow: 0 0 6px rgba(251,113,133,0.3); }
.cyber-btn-rose:hover { background: rgba(251,113,133,0.1); box-shadow: 0 0 15px rgba(251,113,133,0.2); }
</style>
