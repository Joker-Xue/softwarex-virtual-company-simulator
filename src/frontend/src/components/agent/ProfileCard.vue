<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAgentWorldStore } from '@/stores/agentWorld'
import type { AgentMemoryItem } from '@/stores/agentWorld'
import { CAREER_LEVELS, DEPARTMENTS, ACTION_LABELS, AVATAR_COLORS } from '@/constants/companyMap'
import request from '@/utils/request'

const store = useAgentWorldStore()

const emit = defineEmits<{
  'open-chat': [id: number]
}>()

const displayAgent = computed(() => store.selectedAgent || store.myProfile)
const isMe = computed(() => !store.selectedAgent || store.selectedAgent.id === store.myProfile?.id)
const personalityTrace = computed(() => store.personalityTrace)
const effectiveMultipliers = computed(() => personalityTrace.value?.effective_multipliers || {})

// Tab state
const activeTab = ref('info')

// ── DateRelated ──
// Current time（Updated every minutes，Used to highlight Current schedule items）
const currentTime = ref(getCurrentTimeStr())
let timeTimer: ReturnType<typeof setInterval> | null = null

function getCurrentTimeStr(): string {
  const now = new Date()
  return now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0')
}

onMounted(() => {
  timeTimer = setInterval(() => {
    currentTime.value = getCurrentTimeStr()
  }, 60000) // Update every minutes
  store.fetchPersonalityTrace()
})

onUnmounted(() => {
  if (timeTimer) clearInterval(timeTimer)
})

// Schedule data
const schedule = computed(() => {
  return displayAgent.value?.daily_schedule || []
})

// JudgingWhether a certain schedule item is the Current activity time period
function isCurrentBlock(index: number): boolean {
  if (!schedule.value.length) return false
  const now = currentTime.value
  const entry = schedule.value[index]
  const nextEntry = schedule.value[index + 1]
  // Current time >= the msgsproject time and < next msgsproject time（Or the last msgs）
  if (entry.time <= now && (!nextEntry || nextEntry.time > now)) {
    return true
  }
  return false
}

// Activity name to color mapping
function getActivityColor(activity: string): string {
  const colorMap: Record<string, string> = {
    'Work': '#6366f1',
    'Rest': '#10b981',
    'lunch': '#f59e0b',
    'break': '#14b8a6',
    'Social': '#ec4899',
    'get off work': '#94a3b8',
  }
  return colorMap[activity] || '#6366f1'
}

// Room type tag
const ROOM_TYPE_LABELS: Record<string, string> = {
  office: 'office',
  cafeteria: 'Cafe',
  lounge: 'Lobby',
  meeting: 'Meeting Room',
  ceo_office: 'CEO Office',
}

// Memory state
const memoryPage = ref(1)
const memoryPageSize = 20
const memoryTypeFilter = ref('')
const memoryLoading = ref(false)

// Memory type colors
const MEMORY_TYPE_COLORS: Record<string, string> = {
  interaction: '#3b82f6',
  task: '#10b981',
  observation: '#94a3b8',
  career: '#f59e0b',
  social: '#a855f7',
}

const MEMORY_TYPE_LABELS: Record<string, string> = {
  interaction: 'interactive',
  task: 'Task',
  observation: 'observe',
  career: 'Profession',
  social: 'Social',
}

function clearSelection() {
  store.selectedAgent = null
  activeTab.value = 'info'
}

async function addFriend() {
  if (!store.selectedAgent) return
  try {
    await store.sendFriendRequest(store.selectedAgent.id)
    ElMessage.success('Friend application has been sent')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'Send failed，Please try again later')
  }
}

async function loadMemories() {
  if (!isMe.value) return
  memoryLoading.value = true
  try {
    await store.fetchMemories(
      memoryPage.value,
      memoryPageSize,
      memoryTypeFilter.value || undefined,
    )
  } finally {
    memoryLoading.value = false
  }
}

function onMemoryTypeChange() {
  memoryPage.value = 1
  loadMemories()
}

function onMemoryPageChange(page: number) {
  memoryPage.value = page
  loadMemories()
}

function getImportanceStars(importance: number): string {
  const filled = Math.min(5, Math.ceil(importance / 2))
  return '\u2605'.repeat(filled) + '\u2606'.repeat(5 - filled)
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return ''
  const now = new Date()
  const date = new Date(dateStr)
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin} min ago`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour} h ago`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay < 30) return `${diffDay} d ago`
  const diffMonth = Math.floor(diffDay / 30)
  return `${diffMonth} months ago`
}

// When switching to memories tab, load them
watch(activeTab, (val) => {
  if (val === 'memories' && isMe.value) {
    loadMemories()
  }
  if (val === 'salary' && isMe.value) {
    fetchSalaryInfo()
  }
})

// ── CompensationRelated ──
const salaryInfo = ref<any>(null)
const salaryHistory = ref<any[]>([])
const salaryLoading = ref(false)

async function fetchSalaryInfo() {
  salaryLoading.value = true
  try {
    const [infoRes, histRes] = await Promise.allSettled([
      request.get('/api/agent/salary/info'),
      request.get('/api/agent/salary/history'),
    ])
    if (infoRes.status === 'fulfilled') salaryInfo.value = infoRes.value.data
    if (histRes.status === 'fulfilled') salaryHistory.value = Array.isArray(histRes.value.data) ? histRes.value.data : []
  } finally {
    salaryLoading.value = false
  }
}
</script>

<template>
  <div class="profile-card" v-if="displayAgent">
    <div v-if="!isMe" class="back-btn" @click="clearSelection">&larr; BackMy Role</div>

    <div class="card-header">
      <div class="avatar" :style="{ background: AVATAR_COLORS[displayAgent.avatar_key] || '#6366f1', boxShadow: '0 0 12px ' + (AVATAR_COLORS[displayAgent.avatar_key] || '#6366f1') }">
        {{ displayAgent.nickname[0] }}
      </div>
      <div class="header-info">
        <div class="nickname">{{ displayAgent.nickname }}</div>
        <div class="meta">
          <span class="level-badge">{{ CAREER_LEVELS[displayAgent.career_level]?.title }}</span>
          <span class="dept">{{ DEPARTMENTS[displayAgent.department] || displayAgent.department }}</span>
        </div>
        <div class="mbti-tag cyber-badge cyber-badge-violet">{{ displayAgent.mbti }}</div>
      </div>
    </div>

    <!-- Tabs -->
    <el-tabs v-model="activeTab" class="profile-tabs">
      <el-tab-pane label="Info" name="info" />
      <el-tab-pane label="Today's Schedule" name="schedule" />
      <el-tab-pane v-if="isMe" label="Memories" name="memories" />
      <el-tab-pane v-if="isMe" label="Compensation" name="salary" />
    </el-tabs>

    <!-- Info Tab -->
    <template v-if="activeTab === 'info'">
      <!-- property radar（Simplified to msgs graph） -->
      <div class="attrs-section">
        <div class="attr-bar" v-for="(label, key) in { attr_communication: 'Communication', attr_leadership: 'Leadership', attr_creativity: 'Creativity', attr_technical: 'Technical Skill', attr_teamwork: 'Teamwork', attr_diligence: 'Diligence' }" :key="key">
          <span class="bar-label">{{ label }}</span>
          <div class="bar-track cyber-progress">
            <div class="bar-fill cyber-progress-bar" :style="{ width: (displayAgent as any)[key] + '%' }" />
          </div>
          <span class="bar-val">{{ (displayAgent as any)[key] }}</span>
        </div>
      </div>

      <!-- MBTI Influence -->
      <div class="mbti-influence" v-if="effectiveMultipliers.work_speed">
        <div class="influence-title">{{ store.myProfile?.mbti }} personality influence</div>
        <div class="influence-grid">
          <div class="inf-item">
            <span class="inf-label">Work Speed</span>
            <span class="inf-value" :class="{ boosted: effectiveMultipliers.work_speed > 1 }">{{ effectiveMultipliers.work_speed?.toFixed(2) }}x</span>
          </div>
          <div class="inf-item">
            <span class="inf-label">Social Bonus</span>
            <span class="inf-value" :class="{ boosted: effectiveMultipliers.social_bonus > 1 }">{{ effectiveMultipliers.social_bonus?.toFixed(2) }}x</span>
          </div>
          <div class="inf-item">
            <span class="inf-label">XP Multiplier</span>
            <span class="inf-value" :class="{ boosted: effectiveMultipliers.xp_bonus > 1 }">{{ effectiveMultipliers.xp_bonus?.toFixed(2) }}x</span>
          </div>
          <div class="inf-item">
            <span class="inf-label">Career Tendency</span>
            <span class="inf-value career">{{ effectiveMultipliers.career_tendency === 'technical' ? 'technology' : 'manage' }}</span>
          </div>
        </div>
      </div>

      <!-- Level progress -->
      <div class="level-progress" v-if="isMe && store.nextLevel">
        <div class="progress-label">
          Next Level: {{ store.nextLevel.title }}
          (Tasks {{ store.myProfile!.tasks_completed }}/{{ store.nextLevel.tasksRequired }}，
          XP {{ store.myProfile!.xp }}/{{ store.nextLevel.xpRequired }})
        </div>
        <el-progress
          :percentage="Math.min(100, Math.round(store.myProfile!.xp / store.nextLevel.xpRequired * 100))"
          :stroke-width="8"
          color="#6366f1"
        />
      </div>

      <!-- state -->
      <div class="status-row">
        <span>Status: {{ ACTION_LABELS[displayAgent.current_action] || 'Idle' }}</span>
        <span>Position: ({{ displayAgent.pos_x }}, {{ displayAgent.pos_y }})</span>
      </div>

      <!-- Action button -->
      <div v-if="!isMe" class="action-btns">
        <button class="cyber-btn" @click="addFriend">Add Friend</button>
        <button class="cyber-btn cyber-btn-violet" @click="emit('open-chat', displayAgent!.id)">Message</button>
      </div>
    </template>

    <!-- Schedule Tab (Today's Schedule) -->
    <template v-if="activeTab === 'schedule'">
      <div class="schedule-section">
        <div v-if="schedule.length > 0" class="schedule-timeline-wrap cyber-scroll">
          <el-timeline>
            <el-timeline-item
              v-for="(entry, idx) in schedule"
              :key="idx"
              :color="isCurrentBlock(idx) ? getActivityColor(entry.activity) : '#64748b'"
              :hollow="!isCurrentBlock(idx)"
              :size="isCurrentBlock(idx) ? 'large' : 'normal'"
            >
              <div class="schedule-item" :class="{ 'is-current': isCurrentBlock(idx) }">
                <span class="schedule-time">{{ entry.time }}</span>
                <span
                  class="schedule-activity"
                  :style="{ color: isCurrentBlock(idx) ? getActivityColor(entry.activity) : '#64748b' }"
                >
                  {{ entry.activity }}
                </span>
                <span class="schedule-room-tag">{{ ROOM_TYPE_LABELS[entry.room_type] || entry.room_type }}</span>
                <span class="schedule-current-tag" v-if="isCurrentBlock(idx)">Current</span>
              </div>
            </el-timeline-item>
          </el-timeline>
        </div>
        <div v-else class="schedule-empty">No schedule available</div>
      </div>
    </template>

    <!-- Memories Tab -->
    <template v-if="activeTab === 'memories' && isMe">
      <div class="memory-filter">
        <el-select
          v-model="memoryTypeFilter"
          placeholder="All Types"
          clearable
          size="small"
          @change="onMemoryTypeChange"
        >
          <el-option label="All Types" value="" />
          <el-option
            v-for="(label, key) in MEMORY_TYPE_LABELS"
            :key="key"
            :label="label"
            :value="key"
          />
        </el-select>
        <span class="memory-count">Total {{ store.memoriesTotalCount }} memories</span>
      </div>

      <div v-loading="memoryLoading" class="memory-timeline-wrap cyber-scroll">
        <el-timeline v-if="store.memories.length > 0">
          <el-timeline-item
            v-for="mem in store.memories"
            :key="mem.id"
            :color="MEMORY_TYPE_COLORS[mem.memory_type] || '#94a3b8'"
            :timestamp="timeAgo(mem.created_at)"
            placement="top"
          >
            <div class="memory-item">
              <div class="memory-content">{{ mem.content }}</div>
              <div class="memory-meta">
                <span
                  class="memory-type-tag"
                  :style="{ background: MEMORY_TYPE_COLORS[mem.memory_type] || '#94a3b8' }"
                >
                  {{ MEMORY_TYPE_LABELS[mem.memory_type] || mem.memory_type }}
                </span>
                <span class="memory-importance" :title="`Importance: ${mem.importance}/10`">
                  {{ getImportanceStars(mem.importance) }}
                </span>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
        <div v-else class="memory-empty">No memories yet</div>
      </div>

      <div class="memory-pagination" v-if="store.memoriesTotalCount > memoryPageSize">
        <el-pagination
          small
          layout="prev, pager, next"
          :total="store.memoriesTotalCount"
          :page-size="memoryPageSize"
          :current-page="memoryPage"
          @current-change="onMemoryPageChange"
        />
      </div>
    </template>

    <!-- Salary Tab -->
    <template v-if="activeTab === 'salary' && isMe">
      <div v-loading="salaryLoading" class="salary-section">
        <div v-if="salaryInfo" class="salary-overview">
          <div class="salary-main">
            <span class="salary-label">Daily Pay</span>
            <span class="salary-amount">{{ salaryInfo.total }} coins</span>
          </div>
          <div class="salary-details">
            <div class="salary-row">
              <span>Level</span>
              <span>{{ salaryInfo.career_title }} (Lv.{{ salaryInfo.career_level }})</span>
            </div>
            <div class="salary-row">
              <span>Base Salary</span>
              <span>{{ salaryInfo.base_salary }}</span>
            </div>
            <div class="salary-row">
              <span>Performance Bonus</span>
              <span>+{{ salaryInfo.performance_bonus }} ({{ salaryInfo.performance_rate }}%)</span>
            </div>
          </div>
        </div>
        <div v-if="salaryHistory.length > 0" class="salary-history">
          <h4>Recent Pay Records</h4>
          <div v-for="log in salaryHistory" :key="log.id" class="salary-log-item">
            <span class="log-desc">{{ log.description }}</span>
            <span class="log-amount">+{{ log.amount }}</span>
            <span class="log-date">{{ log.paid_at ? new Date(log.paid_at).toLocaleDateString() : '' }}</span>
          </div>
        </div>
        <div v-else-if="!salaryLoading" class="salary-empty">No pay records yet</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.profile-card {
  display: flex; flex-direction: column; gap: 16px;
  background: var(--bg-surface); padding: 16px; border-radius: var(--radius-md);
  border: 1px solid var(--border-glow);
  font-family: var(--font-body);
}
.back-btn {
  font-size: 15px; color: var(--accent-cyan); cursor: pointer;
  text-shadow: 0 0 6px rgba(34,211,238,0.3);
  transition: color var(--duration-fast);
}
.back-btn:hover { color: var(--accent-violet); }
.card-header { display: flex; gap: 12px; align-items: center; }
.avatar {
  width: 48px; height: 48px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 22px; font-weight: 700; flex-shrink: 0;
  border: 2px solid rgba(255,255,255,0.15);
}
.header-info { flex: 1; min-width: 0; }
.nickname {
  font-size: 20px; font-weight: 700; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.meta { display: flex; gap: 8px; align-items: center; min-width: 0; margin-top: 2px; }
.level-badge {
  font-family: var(--font-mono); font-size: 13px; padding: 1px 8px;
  border-radius: 8px; background: rgba(251,191,36,0.1);
  color: var(--accent-amber); font-weight: 600;
  border: 1px solid rgba(251,191,36,0.25);
  text-shadow: 0 0 6px rgba(251,191,36,0.3);
}
.dept { font-size: 14px; color: var(--text-muted); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mbti-tag { margin-top: 4px; }
.attrs-section { display: flex; flex-direction: column; gap: 8px; }
.attr-bar { display: flex; align-items: center; gap: 8px; min-width: 0; }
.bar-label { width: 92px; font-size: 14px; color: var(--text-muted); flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-track { flex: 1; }
.bar-fill { transition: width 0.3s; }
.bar-val {
  width: 28px; font-size: 14px; font-weight: 600; text-align: right;
  color: var(--accent-cyan); font-family: var(--font-mono);
}
.level-progress { }
.progress-label { font-size: 14px; color: var(--text-muted); margin-bottom: 4px; }
.level-progress :deep(.el-progress-bar__outer) {
  background: rgba(34,211,238,0.08) !important;
}
.level-progress :deep(.el-progress-bar__inner) {
  background: linear-gradient(90deg, var(--accent-cyan), var(--accent-violet)) !important;
  box-shadow: 0 0 8px rgba(34,211,238,0.3);
}
.status-row {
  display: flex; justify-content: space-between;
  font-size: 14px; color: var(--text-muted);
}
.action-btns { display: flex; gap: 8px; }

/* Tabs */
.profile-tabs { margin-bottom: -8px; }
.profile-tabs :deep(.el-tabs__item) {
  font-size: 15px; color: var(--text-muted) !important;
  font-family: var(--font-body);
  transition: color var(--duration-base), text-shadow var(--duration-base);
}
.profile-tabs :deep(.el-tabs__item.is-active) {
  color: var(--accent-cyan) !important;
  text-shadow: 0 0 8px rgba(34,211,238,0.4);
}
.profile-tabs :deep(.el-tabs__active-bar) {
  background: var(--accent-cyan) !important;
  box-shadow: 0 0 8px rgba(34,211,238,0.5);
}
.profile-tabs :deep(.el-tabs__nav-wrap::after) {
  background: var(--border-dim) !important;
}
.profile-tabs :deep(.el-tabs__header) {
  margin: 0 0 8px !important;
}

/* Memory styles */
.memory-filter { display: flex; align-items: center; gap: 8px; }
.memory-filter :deep(.el-select) { width: 120px; }
.memory-filter :deep(.el-input__wrapper) {
  background: var(--bg-card) !important;
  border-color: var(--border-glow) !important;
  box-shadow: none !important;
}
.memory-filter :deep(.el-input__inner) { color: var(--text-primary) !important; }
.memory-count { font-size: 14px; color: var(--text-muted); font-family: var(--font-mono); }

.memory-timeline-wrap {
  max-height: 320px; overflow-y: auto; padding-right: 4px;
}

.memory-item {
  background: var(--bg-card); border-radius: var(--radius-sm);
  padding: 8px 10px;
}
.memory-content {
  font-size: 15px; color: var(--text-primary); line-height: 1.5;
  margin-bottom: 4px;
}
.memory-meta { display: flex; align-items: center; gap: 8px; }
.memory-type-tag {
  font-size: 12px; color: #fff; padding: 1px 6px;
  border-radius: 4px; font-weight: 600;
}
.memory-importance {
  font-size: 14px; color: var(--accent-amber); letter-spacing: 1px;
  text-shadow: 0 0 6px rgba(251,191,36,0.3);
}
.memory-empty {
  text-align: center; padding: 24px 0;
  font-size: 15px; color: var(--text-muted);
}
.memory-pagination { display: flex; justify-content: center; margin-top: 4px; }
.memory-pagination :deep(.el-pagination) { --el-pagination-bg-color: transparent; }
.memory-pagination :deep(.el-pager li) {
  background: var(--bg-card) !important; color: var(--text-muted) !important;
}
.memory-pagination :deep(.el-pager li.is-active) {
  color: var(--accent-cyan) !important;
}

/* Memory timeline */
.memory-timeline-wrap :deep(.el-timeline-item__tail) {
  border-left-color: var(--border-dim);
}
.memory-timeline-wrap :deep(.el-timeline-item__timestamp) {
  color: var(--text-muted) !important; font-family: var(--font-mono); font-size: 13px;
}

/* Schedule styles */
.schedule-section { }
.schedule-timeline-wrap {
  max-height: 360px; overflow-y: auto; padding-right: 4px;
}
.schedule-timeline-wrap :deep(.el-timeline-item__tail) {
  border-left-color: rgba(34,211,238,0.15);
}
.schedule-item {
  display: flex; align-items: center; gap: 8px; min-width: 0;
  padding: 4px 8px; border-radius: var(--radius-sm);
  transition: all 0.2s;
}
.schedule-item.is-current {
  font-weight: 600;
  background: rgba(34,211,238,0.06);
}
.schedule-time {
  font-size: 15px; font-weight: 600; color: var(--text-primary);
  min-width: 42px; font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.schedule-activity { font-size: 15px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.schedule-room-tag {
  font-size: 12px; padding: 0 6px; border-radius: 4px;
  background: rgba(34,211,238,0.06); color: var(--text-muted);
  border: 1px solid var(--border-dim); line-height: 18px;
  max-width: 92px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.schedule-current-tag {
  font-size: 12px; padding: 0 6px; border-radius: 6px;
  background: rgba(34,211,238,0.15); color: var(--accent-cyan);
  border: 1px solid rgba(34,211,238,0.3);
  font-weight: 600; line-height: 18px;
  text-shadow: 0 0 6px rgba(34,211,238,0.4);
}
.schedule-empty {
  text-align: center; padding: 24px 0;
  font-size: 15px; color: var(--text-muted);
}

/* Salary styles */
.salary-section { }
.salary-overview { margin-bottom: 16px; }
.salary-main {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px; border-radius: var(--radius-md);
  background: linear-gradient(135deg, rgba(34,211,238,0.1), rgba(167,139,250,0.1));
  border: 1px solid var(--border-glow);
  margin-bottom: 12px;
}
.salary-label { font-size: 15px; color: var(--text-muted); }
.salary-amount {
  font-size: 22px; font-weight: 700; color: var(--accent-amber);
  font-family: var(--font-mono);
  text-shadow: 0 0 10px rgba(251,191,36,0.4);
}
.salary-details { }
.salary-row {
  display: flex; justify-content: space-between; font-size: 15px;
  padding: 4px 0; color: var(--text-muted);
}
.salary-row span:last-child {
  font-weight: 600; color: var(--text-primary);
  font-family: var(--font-mono);
}
.salary-history h4 {
  font-size: 15px; color: var(--text-muted); margin: 0 0 8px;
  font-family: var(--font-display); letter-spacing: 0.5px;
}
.salary-log-item {
  display: flex; gap: 8px; align-items: center; padding: 6px 0;
  border-bottom: 1px solid var(--border-dim); font-size: 14px;
}
.log-desc { flex: 1; color: var(--text-primary); }
.log-amount {
  font-weight: 600; color: var(--accent-emerald);
  font-family: var(--font-mono);
  text-shadow: 0 0 6px rgba(52,211,153,0.3);
}
.log-date { color: var(--text-muted); font-size: 13px; font-family: var(--font-mono); }
.salary-empty { text-align: center; padding: 24px 0; font-size: 15px; color: var(--text-muted); }

/* MBTI Influence */
.mbti-influence { margin-top: 16px; padding: 12px; background: rgba(167,139,250,0.05); border: 1px solid rgba(167,139,250,0.15); border-radius: 6px; }
.influence-title { font-family: var(--font-display); font-size: 13px; color: var(--accent-violet); letter-spacing: 1px; margin-bottom: 10px; text-transform: uppercase; }
.influence-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.inf-item { display: flex; justify-content: space-between; gap: 8px; min-width: 0; padding: 4px 0; }
.inf-label { font-family: var(--font-body); font-size: 13px; color: var(--text-muted); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inf-value { font-family: var(--font-mono); font-size: 14px; font-weight: 700; color: var(--text-primary); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inf-value.boosted { color: var(--accent-cyan); }
.inf-value.career { color: var(--accent-violet); }
</style>
