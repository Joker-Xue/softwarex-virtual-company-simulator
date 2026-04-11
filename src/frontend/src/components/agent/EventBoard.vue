<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useAgentWorldStore } from '@/stores/agentWorld'
import request from '@/utils/request'

const store = useAgentWorldStore()

interface EventDecision {
  joined: boolean
  interest_score: number
  reason: string
}

interface AgentEvent {
  id: number
  name: string
  event_type: string
  description: string
  scheduled_at: string
  duration_minutes: number
  participants: number[]
  participant_count: number
  max_participants: number
  rewards_xp: number
  rewards_coins: number
  is_active: string
  room_name?: string
  agent_decision?: EventDecision
}

const events = ref<AgentEvent[]>([])
const now = ref(Date.now())
let refreshTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

async function loadEvents() {
  try {
    const { data } = await request.get('/api/event/list')
    const raw: AgentEvent[] = Array.isArray(data) ? data : (data?.data || [])
    if (store.myProfile) {
      for (const evt of raw) {
        const mbti = store.myProfile.mbti || 'ISTJ'
        evt.agent_decision = computeLocalDecision(mbti, evt, store.myProfile)
      }
    }
    events.value = raw
  } catch { /* ignore */ }
}

onMounted(async () => {
  await loadEvents()
  refreshTimer = setInterval(loadEvents, 30000)
  clockTimer = setInterval(() => { now.value = Date.now() }, 1000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (clockTimer) clearInterval(clockTimer)
})

function computeLocalDecision(mbti: string, event: any, agent: any): EventDecision {
  let interest = 50
  const reasons: string[] = []
  const etype = event.event_type || ''
  const ename = event.name || ''

  const isSocial = ['team_building', 'tea_break', 'welcome', 'birthday'].includes(etype) || ename.includes('Team Building') || ename.includes('Social')
  const isTech = ['tech_talk', 'training', 'workshop'].includes(etype) || ename.includes('technology') || ename.includes('Training')

  if (mbti[0] === 'E') {
    if (isSocial) { interest += 30; reasons.push('E type social preference +30') }
    else { interest += 5; reasons.push('E type Base+5') }
  } else {
    if (isSocial) { interest -= 20; reasons.push('I type social avoidance -20') }
    if (isTech) { interest += 20; reasons.push('IType Preference Technology +20') }
  }

  if (mbti[2] === 'T' && isTech) { interest += 15; reasons.push('T type technical interest +15') }
  if (mbti[2] === 'F' && isSocial) { interest += 15; reasons.push('F type collaboration preference +15') }

  if (mbti[3] === 'J' && agent.current_action === 'work') { interest -= 15; reasons.push('J type unwilling to interrupt -15') }
  if (mbti[3] === 'P') { interest += 10; reasons.push('P type casual +10') }

  const comm = agent.attr_communication || 50
  if (isSocial) { const b = Math.floor(comm / 10); interest += b; reasons.push('Communication' + comm + '+' + b) }

  interest = Math.max(0, Math.min(100, interest))
  return {
    joined: interest >= 50,
    interest_score: interest,
    reason: reasons.join(', ') + ' → preference score' + interest + '%',
  }
}

function formatTime(iso: string): string {
  if (!iso) return '--'
  const d = new Date(iso)
  const month = d.getMonth() + 1
  const day = d.getDate()
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${month}/${day} ${h}:${m}`
}

function getCountdown(iso: string): string {
  const target = new Date(iso).getTime()
  const diff = target - now.value
  if (diff <= 0) return 'starting soon'
  const mins = Math.floor(diff / 60000)
  const hrs = Math.floor(mins / 60)
  if (hrs > 0) return `${hrs}h${mins % 60}mafter`
  return `${mins}mafter`
}

function getStatusLabel(is_active: string): string {
  return { upcoming: 'starting soon', ongoing: 'In Progress', finished: 'ended', active: 'In Progress' }[is_active] || is_active
}

const typeLabels: Record<string, string> = {
  tea_break: 'Afternoon Tea', team_building: 'Team Building', birthday: 'Birthday Party',
  holiday: 'Holiday Event', milestone: 'Milestone', dept_award: 'Department Award',
  emergency: 'Emergency Mobilization', welcome: 'Welcome', tech_talk: 'tech sharing',
  training: 'Training', workshop: 'Workshop',
}
const typeColors: Record<string, string> = {
  tea_break: 'var(--accent-amber)', team_building: 'var(--accent-violet)',
  birthday: 'var(--accent-rose)', holiday: 'var(--accent-emerald)',
  milestone: 'var(--accent-cyan)', dept_award: 'var(--accent-emerald)',
  emergency: 'var(--accent-rose)', welcome: 'var(--accent-cyan)',
}
</script>

<template>
  <div class="event-panel">
    <div class="section-header">
      <span class="header-dot" style="background: var(--accent-violet)"></span>
      <span class="header-text">AIactivity decisions</span>
      <span class="event-count">{{ events.length }} Item</span>
    </div>

    <div v-if="events.length === 0" class="empty-text">No Activity</div>

    <div v-for="event in events" :key="event.id" class="event-card cyber-card"
      :class="{ 'card-ongoing': event.is_active === 'ongoing' || event.is_active === 'active', 'card-finished': event.is_active === 'finished' }">
      <div class="event-top">
        <span class="event-type" :style="{ color: typeColors[event.event_type] || 'var(--accent-cyan)', borderColor: typeColors[event.event_type] || 'var(--accent-cyan)' }">
          {{ typeLabels[event.event_type] || event.event_type }}
        </span>
        <span class="event-name">{{ event.name }}</span>
        <span class="status-badge"
          :class="{
            'status-upcoming': event.is_active === 'upcoming',
            'status-ongoing': event.is_active === 'ongoing' || event.is_active === 'active',
            'status-finished': event.is_active === 'finished',
          }">
          {{ getStatusLabel(event.is_active) }}
        </span>
      </div>

      <p class="event-desc" v-if="event.description">{{ event.description }}</p>

      <!-- Time & Location Row -->
      <div class="event-info-row">
        <span class="info-item">
          <span class="info-icon">⏰</span>
          {{ formatTime(event.scheduled_at) }}
          <span v-if="event.is_active === 'upcoming'" class="countdown">（{{ getCountdown(event.scheduled_at) }}）</span>
        </span>
        <span class="info-item" v-if="event.room_name">
          <span class="info-icon">📍</span>{{ event.room_name }}
        </span>
        <span class="info-item">
          <span class="info-icon">⏱</span>{{ event.duration_minutes }}min
        </span>
      </div>

      <!-- Participants -->
      <div class="participants-row">
        <span class="info-icon">👥</span>
        <span class="part-count">{{ event.participant_count }} / {{ event.max_participants }}</span>
        <div class="part-bar">
          <div class="part-fill" :style="{ width: Math.min(100, event.participant_count / event.max_participants * 100) + '%' }"></div>
        </div>
      </div>

      <!-- Decision -->
      <div v-if="event.agent_decision" class="decision-row">
        <span class="decision-tag" :class="{ joined: event.agent_decision.joined, rejected: !event.agent_decision.joined }">
          {{ event.agent_decision.joined ? '✓ AI decision-making participation' : '✗ AI decision reject' }}
        </span>
        <div class="interest-bar">
          <div class="interest-track">
            <div class="interest-fill" :style="{ width: event.agent_decision.interest_score + '%', background: event.agent_decision.interest_score >= 50 ? 'var(--accent-emerald)' : 'var(--accent-rose)' }"></div>
          </div>
          <span class="interest-score">{{ event.agent_decision.interest_score }}%</span>
        </div>
      </div>

      <div class="decision-reason" v-if="event.agent_decision?.reason">
        {{ event.agent_decision.reason }}
      </div>

      <div class="event-meta">
        <span v-if="event.rewards_xp">+{{ event.rewards_xp }}XP</span>
        <span v-if="event.rewards_coins">+{{ event.rewards_coins }}gold</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.event-panel { padding: 12px; }
.section-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.header-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.header-text { font-family: var(--font-body); font-weight: 600; font-size: 13px; color: var(--text-primary); }
.event-count { margin-left: auto; font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }
.empty-text { font-family: var(--font-body); font-size: 12px; color: var(--text-muted); text-align: center; padding: 20px 0; }

.event-card { padding: 12px; margin-bottom: 10px; transition: box-shadow 0.3s; }
.card-ongoing { box-shadow: 0 0 8px rgba(52,211,153,0.25); border-color: rgba(52,211,153,0.4) !important; }
.card-finished { opacity: 0.55; }

.event-top { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.event-type { font-family: var(--font-mono); font-size: 10px; padding: 1px 6px; border: 1px solid; border-radius: 3px; flex-shrink: 0; }
.event-name { font-family: var(--font-body); font-size: 13px; font-weight: 600; color: var(--text-primary); flex: 1; }

.status-badge { font-family: var(--font-mono); font-size: 10px; padding: 2px 7px; border-radius: 3px; font-weight: 700; flex-shrink: 0; }
.status-upcoming { color: var(--accent-cyan); background: rgba(34,211,238,0.1); border: 1px solid rgba(34,211,238,0.3); }
.status-ongoing { color: var(--accent-emerald); background: rgba(52,211,153,0.12); border: 1px solid rgba(52,211,153,0.4); animation: pulse-green 1.5s ease-in-out infinite; }
.status-finished { color: var(--text-muted); background: rgba(100,116,139,0.1); border: 1px solid rgba(100,116,139,0.25); }

@keyframes pulse-green {
  0%, 100% { box-shadow: none; }
  50% { box-shadow: 0 0 6px rgba(52,211,153,0.5); }
}

.event-desc { font-family: var(--font-body); font-size: 11px; color: var(--text-muted); margin: 0 0 8px; line-height: 1.4; }

.event-info-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 6px; }
.info-item { font-family: var(--font-mono); font-size: 11px; color: var(--text-secondary); display: flex; align-items: center; gap: 3px; }
.info-icon { font-size: 11px; }
.countdown { color: var(--accent-amber); margin-left: 2px; }

.participants-row { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.part-count { font-family: var(--font-mono); font-size: 11px; color: var(--text-secondary); min-width: 40px; }
.part-bar { flex: 1; height: 3px; background: rgba(100,116,139,0.2); border-radius: 2px; overflow: hidden; }
.part-fill { height: 100%; background: var(--accent-violet); border-radius: 2px; transition: width 0.4s ease; }

.decision-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.decision-tag { font-family: var(--font-mono); font-size: 10px; padding: 2px 8px; border-radius: 3px; font-weight: 700; flex-shrink: 0; }
.decision-tag.joined { color: var(--accent-emerald); background: rgba(52,211,153,0.1); border: 1px solid rgba(52,211,153,0.3); }
.decision-tag.rejected { color: var(--accent-rose); background: rgba(251,113,133,0.1); border: 1px solid rgba(251,113,133,0.3); }

.interest-bar { display: flex; align-items: center; gap: 6px; flex: 1; }
.interest-track { flex: 1; height: 4px; background: rgba(100,116,139,0.15); border-radius: 2px; overflow: hidden; }
.interest-fill { height: 100%; border-radius: 2px; transition: width 0.5s ease; }
.interest-score { font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: var(--text-secondary); min-width: 30px; text-align: right; }

.decision-reason { font-family: var(--font-body); font-size: 11px; color: var(--text-muted); padding: 6px 8px; background: rgba(167,139,250,0.05); border-left: 2px solid var(--accent-violet); border-radius: 0 3px 3px 0; margin-bottom: 8px; line-height: 1.4; }

.event-meta { display: flex; gap: 10px; font-family: var(--font-mono); font-size: 10px; color: var(--text-muted); }
</style>
