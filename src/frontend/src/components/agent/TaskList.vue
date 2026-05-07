<script setup lang="ts">
import { onMounted, onUnmounted, computed } from 'vue'
import { useAgentWorldStore } from '@/stores/agentWorld'

const store = useAgentWorldStore()
let pollTimer: ReturnType<typeof setInterval> | null = null

const emit = defineEmits<{
  (e: 'promotion', data: { level: number; title: string }): void
}>()

onMounted(() => {
  store.fetchTaskStatus()
  store.fetchTasks()
  pollTimer = setInterval(() => store.fetchTaskStatus(), 15000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

const currentTask = computed(() => store.taskStatus?.current_task)
const taskQueue = computed(() => store.taskStatus?.task_queue || [])
const completedTasks = computed(() => (store.tasks || []).filter((t: any) => t.status === 'completed').slice(0, 8))

function diffStars(d: number) {
  return '★'.repeat(d) + '☆'.repeat(5 - d)
}

function alignColor(a: string) {
  if (a === 'high') return 'var(--accent-emerald)'
  if (a === 'low') return 'var(--accent-rose)'
  return 'var(--accent-amber)'
}

function formatDuration(s: number) {
  if (!s || s <= 0) return '0s'
  if (s < 60) return Math.round(s) + 's'
  return Math.round(s / 60) + 'm ' + Math.round(s % 60) + 's'
}

/** parse task descriptionLocation/Contact person metadata in */
function parseTaskMeta(description: string): { location: string; contact: string } {
  if (!description) return { location: '', contact: '' }
  const m = description.match(/^\[Location:([^|]+)\|Contact:([^\]]+)\]/)
  if (m) return { location: m[1].trim(), contact: m[2].trim() }
  return { location: '', contact: '' }
}
</script>

<template>
  <div class="task-panel">
    <!-- Current Task Progress -->
    <div v-if="currentTask" class="current-task cyber-card scan-lines">
      <div class="section-header">
        <span class="header-dot" style="background: var(--accent-cyan)"></span>
        <span class="header-text">Current task</span>
        <span class="task-type-badge">{{ currentTask.task_type || 'project' }}</span>
      </div>
      <div class="task-name">{{ currentTask.name }}</div>
      <div class="task-diff">{{ diffStars(currentTask.difficulty) }}</div>

      <!-- Location & Contact -->
      <div class="task-context" v-if="currentTask.location || currentTask.contact_person">
        <span v-if="currentTask.location" class="ctx-badge loc-badge">
          <span class="ctx-icon">&#x25A3;</span>{{ currentTask.location }}
        </span>
        <span v-if="currentTask.contact_person" class="ctx-badge contact-badge">
          <span class="ctx-icon">&#x25C6;</span>{{ currentTask.contact_person }}
        </span>
      </div>

      <!-- Progress Bar -->
      <div class="progress-container">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: Math.min(currentTask.progress_pct, 100) + '%' }"></div>
        </div>
        <span class="progress-text">{{ currentTask.progress_pct?.toFixed(1) }}%</span>
      </div>

      <div class="time-row">
        <span>Elapsed {{ formatDuration(currentTask.elapsed_s) }}</span>
        <span>Expected {{ formatDuration(currentTask.estimated_duration_s) }}</span>
      </div>

      <!-- Speed Factors -->
      <div class="speed-factors" v-if="currentTask.speed_factors">
        <span class="factor-tag" v-for="(v, k) in currentTask.speed_factors" :key="k">
          {{ k === 'work_speed' ? 'Work Speed' : k === 'tag_affinity' ? 'tag match' : k === 'base_time' ? 'Basetime' : 'The final time consuming' }}
          <strong>{{ v }}</strong>
        </span>
      </div>

      <!-- Selection Reason -->
      <div class="selection-reason" v-if="currentTask.selection_reason">
        <span class="reason-label">Reasons for AI selection</span>
        <span class="reason-text">{{ currentTask.selection_reason }}</span>
      </div>
    </div>

    <div v-else class="no-task cyber-card">
      <div class="section-header">
        <span class="header-dot" style="background: var(--text-muted)"></span>
        <span class="header-text">Current task</span>
      </div>
      <p class="empty-text">AI is selecting the next Task...</p>
    </div>

    <!-- Task Queue -->
    <div class="queue-section">
      <div class="section-header">
        <span class="header-dot" style="background: var(--accent-violet)"></span>
        <span class="header-text">Task queue</span>
        <span class="queue-count">{{ taskQueue.length }}/3 Item</span>
      </div>

      <div v-if="taskQueue.length === 0" class="empty-text">No PendingTask</div>

      <div v-for="(task, i) in taskQueue" :key="task.task_id" class="queue-item" :style="{ animationDelay: Number(i) * 0.05 + 's' }">
        <div class="queue-left">
          <span class="queue-rank">#{{ Number(i) + 1 }}</span>
          <div class="queue-info">
            <span class="queue-name">{{ task.name }}</span>
            <span class="queue-diff">{{ diffStars(task.difficulty) }}</span>
            <div class="queue-context" v-if="task.location || task.contact_person">
              <span v-if="task.location" class="qctx-tag loc-tag">{{ task.location }}</span>
              <span v-if="task.contact_person" class="qctx-tag contact-tag">{{ task.contact_person }}</span>
            </div>
          </div>
        </div>
        <div class="queue-right">
          <div class="score-badge" :style="{ borderColor: alignColor(task.mbti_alignment), color: alignColor(task.mbti_alignment) }">
            {{ task.preference_score }}point
          </div>
          <div class="queue-reason" :title="task.reason">{{ task.reason }}</div>
        </div>
      </div>
    </div>

    <!-- Completed Tasks -->
    <div class="completed-section" v-if="completedTasks.length">
      <div class="section-header">
        <span class="header-dot" style="background: var(--accent-emerald)"></span>
        <span class="header-text">Completed</span>
        <span class="queue-count">{{ completedTasks.length }} Item</span>
      </div>
      <div v-for="task in completedTasks" :key="task.id" class="completed-item">
        <span class="check-icon">&#x2713;</span>
        <div class="completed-info">
          <span class="completed-name">{{ task.title }}</span>
          <span v-if="parseTaskMeta(task.description).location" class="completed-meta">
            {{ parseTaskMeta(task.description).location }} &middot; {{ parseTaskMeta(task.description).contact }}
          </span>
        </div>
        <span class="completed-xp">+{{ task.xp_reward }}XP</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.task-panel { padding: 12px; display: flex; flex-direction: column; gap: 14px; }

.section-header { display: flex; align-items: center; gap: 8px; min-width: 0; margin-bottom: 10px; }
.header-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; box-shadow: 0 0 6px currentColor; }
.header-text { font-family: var(--font-body); font-weight: 600; font-size: 15px; color: var(--text-primary); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.queue-count { margin-left: auto; font-family: var(--font-mono); font-size: 13px; color: var(--text-muted); flex-shrink: 0; }
.task-type-badge { margin-left: auto; font-family: var(--font-mono); font-size: 12px; color: var(--accent-cyan); padding: 1px 8px; border: 1px solid rgba(34,211,238,0.3); border-radius: 3px; text-transform: uppercase; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }

/* Current Task */
.current-task { padding: 14px; position: relative; }
.task-name { font-family: var(--font-body); font-size: 17px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.task-diff { font-size: 13px; color: var(--accent-amber); letter-spacing: 1px; margin-bottom: 8px; }

/* Location & Contact context badges */
.task-context { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.ctx-badge { display: inline-flex; align-items: center; gap: 4px; font-family: var(--font-mono); font-size: 12px; padding: 2px 8px; border-radius: 3px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ctx-icon { font-size: 11px; }
.loc-badge { background: rgba(34,211,238,0.08); border: 1px solid rgba(34,211,238,0.25); color: var(--accent-cyan); }
.contact-badge { background: rgba(167,139,250,0.08); border: 1px solid rgba(167,139,250,0.25); color: var(--accent-violet); }

.progress-container { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.progress-bar { flex: 1; height: 6px; background: rgba(34,211,238,0.1); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--accent-cyan), var(--accent-violet)); border-radius: 3px; transition: width 1s ease; box-shadow: 0 0 8px rgba(34,211,238,0.3); }
.progress-text { font-family: var(--font-mono); font-size: 14px; color: var(--accent-cyan); font-weight: 700; min-width: 45px; text-align: right; }

.time-row { display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); margin-bottom: 10px; }

.speed-factors { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.factor-tag { font-size: 12px; color: var(--text-secondary); background: rgba(34,211,238,0.06); border: 1px solid rgba(34,211,238,0.15); border-radius: 3px; padding: 2px 6px; font-family: var(--font-mono); max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.factor-tag strong { color: var(--accent-cyan); margin-left: 3px; }

.selection-reason { padding: 8px 10px; background: rgba(167,139,250,0.06); border-left: 2px solid var(--accent-violet); border-radius: 0 4px 4px 0; }
.reason-label { font-family: var(--font-mono); font-size: 11px; color: var(--accent-violet); text-transform: uppercase; letter-spacing: 1px; display: block; margin-bottom: 3px; }
.reason-text { font-family: var(--font-body); font-size: 14px; color: var(--text-secondary); line-height: 1.4; }

.no-task { padding: 14px; }
.empty-text { font-family: var(--font-body); font-size: 14px; color: var(--text-muted); text-align: center; padding: 12px 0; }

/* Queue */
.queue-item { display: flex; justify-content: space-between; align-items: flex-start; padding: 8px 10px; background: rgba(17,24,39,0.5); border: 1px solid var(--border-dim, rgba(56,189,248,0.08)); border-radius: 6px; margin-bottom: 6px; animation: fadeSlideIn 0.3s ease both; }
@keyframes fadeSlideIn { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: translateX(0); } }

.queue-left { display: flex; align-items: flex-start; gap: 10px; min-width: 0; flex: 1; }
.queue-rank { font-family: var(--font-mono); font-size: 13px; color: var(--text-muted); width: 22px; flex-shrink: 0; padding-top: 2px; }
.queue-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.queue-name { font-family: var(--font-body); font-size: 14px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.queue-diff { font-size: 11px; color: var(--accent-amber); letter-spacing: 1px; }

/* Queue context tags */
.queue-context { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 3px; }
.qctx-tag { font-family: var(--font-mono); font-size: 11px; padding: 1px 5px; border-radius: 2px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.loc-tag { background: rgba(34,211,238,0.07); color: var(--accent-cyan); border: 1px solid rgba(34,211,238,0.2); }
.contact-tag { background: rgba(167,139,250,0.07); color: var(--accent-violet); border: 1px solid rgba(167,139,250,0.2); }

.queue-right { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; flex-shrink: 0; max-width: 45%; margin-left: 8px; }
.score-badge { font-family: var(--font-mono); font-size: 13px; font-weight: 700; padding: 1px 6px; border: 1px solid; border-radius: 3px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.queue-reason { font-family: var(--font-body); font-size: 12px; color: var(--text-muted); max-width: 120px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Completed */
.completed-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.03); }
.check-icon { color: var(--accent-emerald); font-size: 14px; flex-shrink: 0; }
.completed-info { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.completed-name { font-family: var(--font-body); font-size: 14px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.completed-meta { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); opacity: 0.6; }
.completed-xp { font-family: var(--font-mono); font-size: 12px; color: var(--accent-emerald); flex-shrink: 0; }
</style>
