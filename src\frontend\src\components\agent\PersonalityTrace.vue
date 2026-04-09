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
  const labels: Record<string, string> = { work: '工作', chat: '社交', rest: '休息', move_to: '走动', meeting: '会议' }
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
  if (diff < 60) return Math.round(diff) + '秒前'
  if (diff < 3600) return Math.round(diff / 60) + '分钟前'
  if (diff < 86400) return Math.round(diff / 3600) + '小时前'
  return Math.round(diff / 86400) + '天前'
}
</script>

<template>
  <div class="trace-panel" v-if="trace">
    <!-- Effective Multipliers -->
    <div class="multipliers-bar">
      <div class="mult-item">
        <span class="mult-label">工作速度</span>
        <span class="mult-value" :class="{ boosted: multipliers.work_speed > 1 }">{{ multipliers.work_speed?.toFixed(2) }}x</span>
      </div>
      <div class="mult-item">
        <span class="mult-label">社交加成</span>
        <span class="mult-value" :class="{ boosted: multipliers.social_bonus > 1 }">{{ multipliers.social_bonus?.toFixed(2) }}x</span>
      </div>
      <div class="mult-item">
        <span class="mult-label">经验倍率</span>
        <span class="mult-value" :class="{ boosted: multipliers.xp_bonus > 1 }">{{ multipliers.xp_bonus?.toFixed(2) }}x</span>
      </div>
      <div class="mult-item">
        <span class="mult-label">职业倾向</span>
        <span class="mult-value career">{{ multipliers.career_tendency === 'technical' ? '技术路线' : '管理路线' }}</span>
      </div>
    </div>

    <!-- Action Weight Bars -->
    <div class="weight-section">
      <div class="section-title">行为概率分布</div>
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
      <div class="tend-row"><span class="tend-label">最可能行为</span><span class="tend-value">{{ tendency.most_likely_action }}</span></div>
      <div class="tend-row"><span class="tend-label">最不可能</span><span class="tend-value dim">{{ tendency.least_likely_action }}</span></div>
      <div class="tend-row"><span class="tend-label">偏好任务</span><span class="tend-value">{{ (tendency.preferred_task_tags || []).join(', ') }}</span></div>
      <div class="tend-row"><span class="tend-label">活动参与率</span><span class="tend-value">{{ ((tendency.event_join_rate || 0) * 100).toFixed(0) }}%</span></div>
    </div>

    <!-- Decision Timeline -->
    <div class="timeline-section">
      <div class="section-title">决策时间线 <span class="timeline-count">{{ decisions.length }}</span></div>
      <div class="timeline-list">
        <div v-for="(d, i) in decisions" :key="i" class="timeline-item" :style="{ animationDelay: i * 0.03 + 's' }">
          <div class="tl-icon" :style="{ color: decisionColor(d.type) }">{{ decisionIcon(d.type) }}</div>
          <div class="tl-content">
            <div class="tl-header">
              <span class="tl-type" :style="{ color: decisionColor(d.type) }">
                {{ d.type === 'action_decision' ? '行为决策' : d.type === 'task_assign' ? '任务分配' : d.type === 'task_complete' ? '任务完成' : d.type === 'social' ? '社交互动' : d.type === 'schedule_decision' ? '日程执行' : d.type }}
              </span>
              <span class="tl-time">{{ timeAgo(d.tick_ts) }}</span>
            </div>
            <div class="tl-text">{{ d.explanation || d.reason || d.task_name || '' }}</div>
            <!-- Extra data for task_complete -->
            <div class="tl-tags" v-if="d.type === 'task_complete'">
              <span class="tl-tag">+{{ d.xp_earned }}XP</span>
              <span class="tl-tag">速度{{ d.work_speed }}x</span>
            </div>
            <div class="tl-tags" v-if="d.type === 'task_assign'">
              <span class="tl-tag">偏好{{ d.preference_score }}分</span>
              <span class="tl-tag" :style="{ color: d.alignment === 'high' ? 'var(--accent-emerald)' : d.alignment === 'low' ? 'var(--accent-rose)' : 'var(--accent-amber)' }">{{ d.alignment === 'high' ? '高匹配' : d.alignment === 'low' ? '低匹配' : '中等' }}</span>
            </div>
            <div class="tl-tags" v-if="d.type === 'social'">
              <span class="tl-tag">亲密度+{{ d.affinity_gain }}</span>
              <span class="tl-tag">社交{{ d.social_multiplier }}x</span>
            </div>
            <div class="tl-tags" v-if="d.type === 'action_decision' && d.probabilities">
              <span class="tl-tag" v-for="(p, a) in d.probabilities" :key="a">{{ a === 'work' ? '工作' : a === 'chat' ? '社交' : a === 'rest' ? '休息' : a === 'move_to' ? '走动' : '会议' }}{{ p }}%</span>
            </div>
          </div>
        </div>
        <div v-if="decisions.length === 0" class="empty-text">等待AI产生第一条决策...</div>
      </div>
    </div>
  </div>
  <div v-else class="trace-panel loading-text">加载性格轨迹数据中...</div>
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
