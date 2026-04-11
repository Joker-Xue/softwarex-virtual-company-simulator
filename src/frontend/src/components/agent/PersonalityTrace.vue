<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref } from 'vue'
import { useAgentWorldStore } from '@/stores/agentWorld'

const store = useAgentWorldStore()
let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  store.fetchPersonalityTrace()
  pollTimer = setInterval(() => store.fetchPersonalityTrace(), 30000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

const trace = computed(() => store.personalityTrace)
const multipliers = computed(() => trace.value?.effective_multipliers || {})
const tendency = computed(() => trace.value?.personality_tendency || {})
const decisions = computed(() => {
  const list = trace.value?.recent_decisions || []
  return [...list].reverse().slice(0, 30)
})

const actionWeights = computed(() => {
  const w = tendency.value?.action_probabilities || {}
  const labels: Record<string, string> = { work: 'Work', chat: 'Social', rest: 'Rest', move_to: 'walk around', meeting: 'Meeting' }
  return Object.entries(w)
    .map(([k, v]) => ({ action: k, label: labels[k] || k, pct: v as number }))
    .sort((a, b) => b.pct - a.pct)
})

function decisionIcon(type: string) {
  const icons: Record<string, string> = {
    action_decision: '🎯', schedule_decision: '📅',
    task_assign: '📋', task_complete: '✅',
    social: '💬', event: '🎉',
  }
  return icons[type] || '📌'
}

function decisionColor(type: string) {
  const colors: Record<string, string> = {
    action_decision: 'var(--accent-cyan)', schedule_decision: 'var(--accent-amber)',
    task_assign: 'var(--accent-violet)', task_complete: 'var(--accent-emerald)',
    social: 'var(--accent-rose)', event: 'var(--accent-amber)',
  }
  return colors[type] || 'var(--text-muted)'
}

function timeAgo(ts: string) {
  if (!ts) return ''
  const diff = (Date.now() - new Date(ts).getTime()) / 1000
  if (diff < 60) return Math.round(diff) + 's ago'
  if (diff < 3600) return Math.round(diff / 60) + ' min ago'
  if (diff < 86400) return Math.round(diff / 3600) + ' h ago'
  return Math.round(diff / 86400) + ' d ago'
}
</script>

<template>
  <div class="trace-panel" v-if="trace">
    <!-- Effective Multipliers -->
    <div class="multipliers-bar">
      <div class="mult-item">
        <span class="mult-label">Work Speed</span>
        <span class="mult-value" :class="{ boosted: multipliers.work_speed > 1 }">{{ multipliers.work_speed?.toFixed(2) }}x</span>
      </div>
      <div class="mult-item">
        <span class="mult-label">Social Bonus</span>
        <span class="mult-value" :class="{ boosted: multipliers.social_bonus > 1 }">{{ multipliers.social_bonus?.toFixed(2) }}x</span>
      </div>
      <div class="mult-item">
        <span class="mult-label">XP Multiplier</span>
        <span class="mult-value" :class="{ boosted: multipliers.xp_bonus > 1 }">{{ multipliers.xp_bonus?.toFixed(2) }}x</span>
      </div>
      <div class="mult-item">
        <span class="mult-label">Career Tendency</span>
        <span class="mult-value career">{{ multipliers.career_tendency === 'technical' ? 'Technical Track' : 'Management Track' }}</span>
      </div>
    </div>

    <!-- Action Weight Bars -->
    <div class="weight-section">
      <div class="section-title">Behavior Probability Distribution</div>
      <div v-for="item in actionWeights" :key="item.action" class="weight-row">
        <span class="weight-label">{{ item.label }}</span>
        <div class="weight-track">
          <div class="weight-fill" :style="{ width: item.pct + '%' }"></div>
        </div>
        <span class="weight-pct">{{ item.pct }}%</span>
      </div>
    </div>

    <!-- Tendency Summary -->
    <div class="tendency-section">
      <div class="tend-row"><span class="tend-label">Most Likely Action</span><span class="tend-value">{{ tendency.most_likely_action }}</span></div>
      <div class="tend-row"><span class="tend-label">Least Likely</span><span class="tend-value dim">{{ tendency.least_likely_action }}</span></div>
      <div class="tend-row"><span class="tend-label">Preferred Task Tags</span><span class="tend-value">{{ (tendency.preferred_task_tags || []).join(', ') }}</span></div>
      <div class="tend-row"><span class="tend-label">Event Participation Rate</span><span class="tend-value">{{ ((tendency.event_join_rate || 0) * 100).toFixed(0) }}%</span></div>
    </div>

    <!-- Decision Timeline -->
    <div class="timeline-section">
      <div class="section-title">Decision Timeline <span class="timeline-count">{{ decisions.length }}</span></div>
      <div class="timeline-list">
        <div v-for="(d, i) in decisions" :key="i" class="timeline-item" :style="{ animationDelay: i * 0.03 + 's' }">
          <div class="tl-icon" :style="{ color: decisionColor(d.type) }">{{ decisionIcon(d.type) }}</div>
          <div class="tl-content">
            <div class="tl-header">
              <span class="tl-type" :style="{ color: decisionColor(d.type) }">
                {{ d.type === 'action_decision' ? 'Action Decision' : d.type === 'task_assign' ? 'Task Assignment' : d.type === 'task_complete' ? 'Task Completion' : d.type === 'social' ? 'Social Interaction' : d.type === 'schedule_decision' ? 'Schedule Execution' : d.type }}
              </span>
              <span class="tl-time">{{ timeAgo(d.tick_ts) }}</span>
            </div>
            <div class="tl-text">{{ d.explanation || d.reason || d.task_name || '' }}</div>
            <!-- Extra data for task_complete -->
            <div class="tl-tags" v-if="d.type === 'task_complete'">
              <span class="tl-tag">+{{ d.xp_earned }}XP</span>
              <span class="tl-tag">Speed{{ d.work_speed }}x</span>
            </div>
            <div class="tl-tags" v-if="d.type === 'task_assign'">
              <span class="tl-tag">Preference{{ d.preference_score }}point</span>
              <span class="tl-tag" :style="{ color: d.alignment === 'high' ? 'var(--accent-emerald)' : d.alignment === 'low' ? 'var(--accent-rose)' : 'var(--accent-amber)' }">{{ d.alignment === 'high' ? 'High Match' : d.alignment === 'low' ? 'Low Match' : 'Medium' }}</span>
            </div>
            <div class="tl-tags" v-if="d.type === 'social'">
              <span class="tl-tag">affinity+{{ d.affinity_gain }}</span>
              <span class="tl-tag">Social{{ d.social_multiplier }}x</span>
            </div>
            <div class="tl-tags" v-if="d.type === 'action_decision' && d.probabilities">
              <span class="tl-tag" v-for="(p, a) in d.probabilities" :key="a">{{ a === 'work' ? 'Work' : a === 'chat' ? 'Social' : a === 'rest' ? 'Rest' : a === 'move_to' ? 'walk around' : 'Meeting' }}{{ p }}%</span>
            </div>
          </div>
        </div>
        <div v-if="decisions.length === 0" class="empty-text">Waiting for the AI to produce the first decision...</div>
      </div>
    </div>
  </div>
  <div v-else class="trace-panel loading-text">Loading personality trace data...</div>
</template>

<style scoped>
.trace-panel { padding: 12px; display: flex; flex-direction: column; gap: 16px; }
.loading-text { font-family: var(--font-body); font-size: 12px; color: var(--text-muted); text-align: center; padding: 40px 0; }
.empty-text { font-family: var(--font-body); font-size: 12px; color: var(--text-muted); text-align: center; padding: 16px 0; }

/* Multipliers */
.multipliers-bar { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.mult-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; background: rgba(17,24,39,0.6); border: 1px solid var(--border-dim, rgba(56,189,248,0.08)); border-radius: 6px; }
.mult-label { font-family: var(--font-body); font-size: 11px; color: var(--text-muted); }
.mult-value { font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: var(--text-primary); }
.mult-value.boosted { color: var(--accent-cyan); text-shadow: 0 0 6px rgba(34,211,238,0.4); }
.mult-value.career { color: var(--accent-violet); font-size: 11px; }

/* Weight bars */
.section-title { font-family: var(--font-body); font-weight: 600; font-size: 12px; color: var(--text-primary); margin-bottom: 8px; }
.weight-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.weight-label { font-family: var(--font-body); font-size: 11px; color: var(--text-secondary); width: 36px; flex-shrink: 0; }
.weight-track { flex: 1; height: 6px; background: rgba(34,211,238,0.08); border-radius: 3px; overflow: hidden; }
.weight-fill { height: 100%; background: linear-gradient(90deg, var(--accent-cyan), var(--accent-violet)); border-radius: 3px; transition: width 0.5s ease; }
.weight-pct { font-family: var(--font-mono); font-size: 11px; color: var(--accent-cyan); width: 36px; text-align: right; }

/* Tendency */
.tendency-section { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; background: rgba(17,24,39,0.5); border: 1px solid var(--border-dim, rgba(56,189,248,0.08)); border-radius: 6px; }
.tend-row { display: flex; justify-content: space-between; align-items: center; }
.tend-label { font-family: var(--font-body); font-size: 11px; color: var(--text-muted); }
.tend-value { font-family: var(--font-mono); font-size: 11px; color: var(--text-primary); }
.tend-value.dim { color: var(--text-muted); }

/* Timeline */
.timeline-count { font-family: var(--font-mono); font-size: 10px; color: var(--text-muted); margin-left: 4px; }
.timeline-list { max-height: 400px; overflow-y: auto; }
.timeline-list::-webkit-scrollbar { width: 3px; }
.timeline-list::-webkit-scrollbar-thumb { background: rgba(34,211,238,0.15); border-radius: 2px; }

.timeline-item { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.03); animation: fadeSlideIn 0.3s ease both; }
@keyframes fadeSlideIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

.tl-icon { font-size: 16px; flex-shrink: 0; width: 24px; text-align: center; }
.tl-content { flex: 1; min-width: 0; }
.tl-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px; }
.tl-type { font-family: var(--font-mono); font-size: 10px; font-weight: 600; text-transform: uppercase; }
.tl-time { font-family: var(--font-mono); font-size: 9px; color: var(--text-muted); }
.tl-text { font-family: var(--font-body); font-size: 11px; color: var(--text-secondary); line-height: 1.4; }
.tl-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.tl-tag { font-family: var(--font-mono); font-size: 9px; color: var(--accent-cyan); background: rgba(34,211,238,0.06); border: 1px solid rgba(34,211,238,0.15); border-radius: 2px; padding: 1px 5px; }
</style>
