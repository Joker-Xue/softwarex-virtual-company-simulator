<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import request from '@/utils/request'
import { ElMessage } from 'element-plus'

const activeTab = ref('personal')
const loading = ref(false)

// ── Personal data ──
const personalData = ref<any>(null)
// ── Company data ──
const companyData = ref<any>(null)

// ── Chart refs ──
const xpChartRef = ref<HTMLElement>()
const taskPieRef = ref<HTMLElement>()
const deptBarRef = ref<HTMLElement>()
const levelPieRef = ref<HTMLElement>()

let xpChart: echarts.ECharts | null = null
let taskPieChart: echarts.ECharts | null = null
let deptBarChart: echarts.ECharts | null = null
let levelPieChart: echarts.ECharts | null = null

function handleResize() {
  xpChart?.resize()
  taskPieChart?.resize()
  deptBarChart?.resize()
  levelPieChart?.resize()
}

// ── Fetch data ──
async function fetchPersonal() {
  loading.value = true
  try {
    const { data } = await request.get('/api/agent/analytics/personal')
    personalData.value = data
    await nextTick()
    renderXpChart()
    renderTaskPie()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || 'Failed to fetch personal data')
  } finally {
    loading.value = false
  }
}

async function fetchCompany() {
  loading.value = true
  try {
    const { data } = await request.get('/api/agent/analytics/company')
    companyData.value = data
    await nextTick()
    renderDeptBar()
    renderLevelPie()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || 'Failed to fetch company data')
  } finally {
    loading.value = false
  }
}

// ── Chart renderers ──
function renderXpChart() {
  if (!xpChartRef.value || !personalData.value) return
  if (xpChart) xpChart.dispose()
  xpChart = echarts.init(xpChartRef.value, 'dark')
  const hist = personalData.value.xp_history
  xpChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: hist.map((h: any) => h.date), axisLabel: { fontSize: 10, interval: 4, color: '#64748b' }, axisLine: { lineStyle: { color: 'rgba(56,189,248,0.15)' } } },
    yAxis: { type: 'value', name: 'XP', nameTextStyle: { color: '#64748b' }, axisLabel: { color: '#64748b' }, splitLine: { lineStyle: { color: 'rgba(56,189,248,0.08)' } }, axisLine: { lineStyle: { color: 'rgba(56,189,248,0.15)' } } },
    series: [{
      type: 'line',
      data: hist.map((h: any) => h.xp),
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#22d3ee', width: 2 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(34,211,238,0.25)' },
        { offset: 1, color: 'rgba(34,211,238,0.01)' },
      ]) },
    }],
  })
}

function renderTaskPie() {
  if (!taskPieRef.value || !personalData.value) return
  if (taskPieChart) taskPieChart.dispose()
  taskPieChart = echarts.init(taskPieRef.value, 'dark')
  const ts = personalData.value.task_stats
  const pending = ts.total - ts.completed - ts.in_progress
  taskPieChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { fontSize: 11, color: '#64748b' } },
    series: [{
      type: 'pie',
      radius: ['40%', '65%'],
      center: ['50%', '45%'],
      label: { show: false },
      data: [
        { value: ts.completed, name: 'Completed', itemStyle: { color: '#34d399' } },
        { value: ts.in_progress, name: 'In Progress', itemStyle: { color: '#fbbf24' } },
        { value: Math.max(pending, 0), name: 'Pending', itemStyle: { color: '#64748b' } },
      ],
    }],
  })
}

function renderDeptBar() {
  if (!deptBarRef.value || !companyData.value) return
  if (deptBarChart) deptBarChart.dispose()
  deptBarChart = echarts.init(deptBarRef.value, 'dark')
  const ds = companyData.value.department_stats
  const deptNames: Record<string, string> = {
    management: 'Management Floor',
    engineering: 'Engineering',
    product: 'Product',
    marketing: 'Marketing',
    finance: 'Finance',
    hr: 'HR Department',
    operations: 'Operations',
    unassigned: 'Unassigned',
  }
  deptBarChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, textStyle: { fontSize: 11, color: '#64748b' } },
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: ds.map((d: any) => deptNames[d.department] || d.department), axisLabel: { color: '#64748b' }, axisLine: { lineStyle: { color: 'rgba(56,189,248,0.15)' } } },
    yAxis: [
      { type: 'value', name: 'Headcount', position: 'left', nameTextStyle: { color: '#64748b' }, axisLabel: { color: '#64748b' }, splitLine: { lineStyle: { color: 'rgba(56,189,248,0.08)' } }, axisLine: { lineStyle: { color: 'rgba(56,189,248,0.15)' } } },
      { type: 'value', name: 'Average XP', position: 'right', nameTextStyle: { color: '#64748b' }, axisLabel: { color: '#64748b' }, splitLine: { show: false }, axisLine: { lineStyle: { color: 'rgba(56,189,248,0.15)' } } },
    ],
    series: [
      { name: 'Headcount', type: 'bar', data: ds.map((d: any) => d.count), itemStyle: { color: '#22d3ee' } },
      { name: 'Average XP', type: 'bar', yAxisIndex: 1, data: ds.map((d: any) => d.avg_xp), itemStyle: { color: '#fbbf24' } },
    ],
  })
}

function renderLevelPie() {
  if (!levelPieRef.value || !companyData.value) return
  if (levelPieChart) levelPieChart.dispose()
  levelPieChart = echarts.init(levelPieRef.value, 'dark')
  const ld = companyData.value.level_distribution
  const colors = ['#64748b', '#22d3ee', '#60a5fa', '#34d399', '#fbbf24', '#fb7185', '#a78bfa']
  levelPieChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { fontSize: 11, color: '#64748b' } },
    series: [{
      type: 'pie',
      radius: ['35%', '60%'],
      center: ['50%', '42%'],
      label: { show: false },
      data: ld.map((l: any, i: number) => ({
        value: l.count, name: l.title, itemStyle: { color: colors[i % colors.length] },
      })),
    }],
  })
}

// ── Lifecycle ──
watch(activeTab, (tab) => {
  if (tab === 'personal' && !personalData.value) fetchPersonal()
  if (tab === 'company' && !companyData.value) fetchCompany()
  // Re-render charts after tab switch
  nextTick(() => {
    if (tab === 'personal') { renderXpChart(); renderTaskPie() }
    if (tab === 'company') { renderDeptBar(); renderLevelPie() }
  })
})

onMounted(() => {
  fetchPersonal()
  window.addEventListener('resize', handleResize)
})
onUnmounted(() => {
  xpChart?.dispose()
  taskPieChart?.dispose()
  deptBarChart?.dispose()
  levelPieChart?.dispose()
  window.removeEventListener('resize', handleResize)
})
</script>

<template>
  <div class="analytics-dashboard">
    <div class="tab-switch">
      <button :class="{ active: activeTab === 'personal' }" @click="activeTab = 'personal'">
        Personal Data
      </button>
      <button :class="{ active: activeTab === 'company' }" @click="activeTab = 'company'">
        Company Data
      </button>
    </div>

    <div v-loading="loading" class="dashboard-body">
      <!-- ══════ Personal Panel ══════ -->
      <div v-if="activeTab === 'personal' && personalData" class="panel-grid">
        <!-- XP Growth Chart -->
        <div class="card cyber-card card-wide">
          <div class="cyber-header">
            <span class="cyber-header-title">XP Growth Trend (Last 30 Days)</span>
          </div>
          <div ref="xpChartRef" class="chart-box"></div>
        </div>

        <!-- Task Pie -->
        <div class="card cyber-card">
          <div class="cyber-header">
            <span class="cyber-header-title">Task Distribution</span>
          </div>
          <div ref="taskPieRef" class="chart-box"></div>
          <div class="stat-row">
            <span>Total Tasks: <strong class="stat-num">{{ personalData.task_stats.total }}</strong></span>
          </div>
        </div>

        <!-- Social Metrics -->
        <div class="card cyber-card">
          <div class="cyber-header">
            <span class="cyber-header-title">Social Metrics</span>
          </div>
          <div class="metric-list">
            <div class="metric-item">
              <span class="metric-label">Friend Count</span>
              <div class="progress-bar">
                <div class="progress-fill friends" :style="{ width: Math.min(personalData.social_stats.friends_count * 10, 100) + '%' }"></div>
              </div>
              <span class="metric-value metric-cyan">{{ personalData.social_stats.friends_count }}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Send Message</span>
              <div class="progress-bar">
                <div class="progress-fill messages" :style="{ width: Math.min(personalData.social_stats.messages_sent, 100) + '%' }"></div>
              </div>
              <span class="metric-value metric-violet">{{ personalData.social_stats.messages_sent }}</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">Average Affinity</span>
              <div class="progress-bar">
                <div class="progress-fill affinity" :style="{ width: personalData.social_stats.avg_affinity + '%' }"></div>
              </div>
              <span class="metric-value metric-emerald">{{ personalData.social_stats.avg_affinity }}%</span>
            </div>
          </div>
        </div>

        <!-- Top Friends -->
        <div class="card cyber-card card-wide">
          <div class="cyber-header">
            <span class="cyber-header-title">Top 5 Closest Friends</span>
          </div>
          <div v-if="personalData.top_friends.length === 0" class="empty-hint">No friend data yet</div>
          <div v-else class="friend-list">
            <div v-for="(f, idx) in personalData.top_friends" :key="idx" class="friend-row">
              <span class="friend-rank">#{{ Number(idx) + 1 }}</span>
              <span class="friend-name">{{ f.nickname }}</span>
              <div class="affinity-bar-wrap">
                <div class="affinity-bar" :style="{ width: f.affinity + '%' }"></div>
              </div>
              <span class="affinity-val">{{ f.affinity }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ══════ Company Panel ══════ -->
      <div v-if="activeTab === 'company' && companyData" class="panel-grid">
        <!-- Department Bar Chart -->
        <div class="card cyber-card card-wide">
          <div class="cyber-header">
            <span class="cyber-header-title">Department Headcount and Average XP</span>
          </div>
          <div ref="deptBarRef" class="chart-box"></div>
        </div>

        <!-- Level Distribution Pie -->
        <div class="card cyber-card">
          <div class="cyber-header">
            <span class="cyber-header-title">Level Distribution</span>
          </div>
          <div ref="levelPieRef" class="chart-box"></div>
        </div>

        <!-- Active Rooms -->
        <div class="card cyber-card">
          <div class="cyber-header">
            <span class="cyber-header-title">Room Activity</span>
          </div>
          <div class="room-list">
            <div v-for="(r, idx) in companyData.active_rooms.slice(0, 6)" :key="idx" class="room-row">
              <span class="room-name">{{ r.room_name }}</span>
              <div class="room-bar-wrap">
                <div class="room-bar" :style="{ width: (r.capacity > 0 ? Math.min(r.agent_count / r.capacity * 100, 100) : 0) + '%' }"></div>
              </div>
              <span class="room-count">{{ r.agent_count }}/{{ r.capacity }}</span>
            </div>
          </div>
        </div>

        <!-- Leaderboard -->
        <div class="card cyber-card card-wide">
          <div class="cyber-header">
            <span class="cyber-header-title">Top 10 XP Leaderboard</span>
          </div>
          <div class="leaderboard">
            <div class="lb-header">
              <span class="lb-rank">Rank</span>
              <span class="lb-name">Nickname</span>
              <span class="lb-dept">Department</span>
              <span class="lb-level">Level</span>
              <span class="lb-xp">XP</span>
            </div>
            <div v-for="(a, idx) in companyData.top_agents" :key="idx" class="lb-row">
              <span class="lb-rank">{{ Number(idx) + 1 }}</span>
              <span class="lb-name">{{ a.nickname }}</span>
              <span class="lb-dept">{{ { management:'Management Floor', engineering:'Engineering', product:'Product', marketing:'Marketing', finance:'Finance', hr:'HR Department', operations:'Operations', unassigned:'Unassigned' }[a.department] || a.department }}</span>
              <span class="lb-level">Lv.{{ a.career_level }}</span>
              <span class="lb-xp">{{ a.xp }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="!loading && ((activeTab === 'personal' && !personalData) || (activeTab === 'company' && !companyData))" class="empty-hint">
        No data available
      </div>
    </div>
  </div>
</template>

<style scoped>
.analytics-dashboard {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 12px;
  font-family: var(--font-body);
}
.tab-switch {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.tab-switch button {
  flex: 1;
  padding: 8px 0;
  border: 1px solid var(--border-dim);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  cursor: pointer;
  font-size: 13px;
  color: var(--text-muted);
  font-family: var(--font-body);
  transition: all var(--duration-base);
}
.tab-switch button:hover {
  background: var(--bg-hover);
  border-color: var(--border-glow);
}
.tab-switch button.active {
  background: transparent;
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
  text-shadow: 0 0 8px rgba(34,211,238,0.4);
  box-shadow: 0 0 12px rgba(34,211,238,0.12), inset 0 -2px 0 var(--accent-cyan);
}
.dashboard-body {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.panel-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.card {
  padding: 14px;
}
.card-wide {
  grid-column: 1 / -1;
}
.chart-box {
  width: 100%;
  height: 220px;
}
.stat-row {
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}
.stat-num {
  font-family: var(--font-mono);
  color: var(--accent-cyan);
  text-shadow: 0 0 6px rgba(34,211,238,0.3);
}

/* ── Social Metrics ── */
.metric-list { display: flex; flex-direction: column; gap: 14px; }
.metric-item { display: flex; align-items: center; gap: 8px; }
.metric-label { font-size: 12px; color: var(--text-muted); width: 70px; flex-shrink: 0; }
.metric-value {
  font-size: 12px; font-weight: 600; width: 40px; text-align: right;
  font-family: var(--font-mono);
}
.metric-cyan {
  color: var(--accent-cyan);
  text-shadow: 0 0 6px rgba(34,211,238,0.3);
}
.metric-violet {
  color: var(--accent-violet);
  text-shadow: 0 0 6px rgba(167,139,250,0.3);
}
.metric-emerald {
  color: var(--accent-emerald);
  text-shadow: 0 0 6px rgba(52,211,153,0.3);
}
.progress-bar {
  flex: 1;
  height: 6px;
  background: rgba(34,211,238,0.08);
  border-radius: 3px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s var(--ease-out-expo);
}
.progress-fill.friends {
  background: linear-gradient(90deg, var(--accent-cyan), var(--accent-violet));
  box-shadow: 0 0 6px rgba(34,211,238,0.3);
}
.progress-fill.messages {
  background: linear-gradient(90deg, var(--accent-violet), var(--accent-cyan));
  box-shadow: 0 0 6px rgba(167,139,250,0.3);
}
.progress-fill.affinity {
  background: linear-gradient(90deg, var(--accent-emerald), var(--accent-cyan));
  box-shadow: 0 0 6px rgba(52,211,153,0.3);
}

/* ── Top Friends ── */
.friend-list { display: flex; flex-direction: column; gap: 8px; }
.friend-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.friend-rank {
  color: var(--accent-cyan); font-weight: 700; width: 28px;
  font-family: var(--font-mono);
}
.friend-name {
  width: 80px; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.affinity-bar-wrap {
  flex: 1;
  height: 6px;
  background: rgba(34,211,238,0.08);
  border-radius: 3px;
  overflow: hidden;
}
.affinity-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-cyan), var(--accent-violet));
  border-radius: 3px;
  box-shadow: 0 0 6px rgba(34,211,238,0.3);
  transition: width 0.6s var(--ease-out-expo);
}
.affinity-val {
  font-size: 12px; color: var(--text-muted); width: 30px; text-align: right;
  font-family: var(--font-mono);
}

/* ── Room List ── */
.room-list { display: flex; flex-direction: column; gap: 8px; }
.room-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.room-name {
  width: 70px; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.room-bar-wrap {
  flex: 1; height: 6px; background: rgba(34,211,238,0.08); border-radius: 3px; overflow: hidden;
}
.room-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-cyan), var(--accent-emerald));
  border-radius: 3px;
  box-shadow: 0 0 6px rgba(34,211,238,0.25);
  transition: width 0.6s var(--ease-out-expo);
}
.room-count {
  color: var(--text-muted); width: 40px; text-align: right;
  font-family: var(--font-mono);
}

/* ── Leaderboard ── */
.leaderboard { font-size: 12px; }
.lb-header, .lb-row {
  display: flex;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid var(--border-dim);
}
.lb-header { font-weight: 600; color: var(--text-muted); }
.lb-row { color: var(--text-primary); transition: background var(--duration-fast); }
.lb-row:hover { background: var(--bg-hover); }

/* Top 3 glow */
.lb-row:nth-child(2) {
  border-left: 3px solid var(--accent-amber);
  background: rgba(251,191,36,0.04);
}
.lb-row:nth-child(2) .lb-rank {
  color: var(--accent-amber); text-shadow: 0 0 8px rgba(251,191,36,0.4);
}
.lb-row:nth-child(3) {
  border-left: 3px solid var(--accent-cyan);
  background: rgba(34,211,238,0.03);
}
.lb-row:nth-child(3) .lb-rank {
  color: var(--accent-cyan); text-shadow: 0 0 8px rgba(34,211,238,0.4);
}
.lb-row:nth-child(4) {
  border-left: 3px solid var(--accent-violet);
  background: rgba(167,139,250,0.03);
}
.lb-row:nth-child(4) .lb-rank {
  color: var(--accent-violet); text-shadow: 0 0 8px rgba(167,139,250,0.4);
}

.lb-rank { width: 40px; text-align: center; font-family: var(--font-mono); }
.lb-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lb-dept { width: 60px; text-align: center; color: var(--text-muted); }
.lb-level {
  width: 40px; text-align: center; color: var(--accent-violet);
  font-weight: 600; font-family: var(--font-mono);
}
.lb-xp {
  width: 50px; text-align: right; font-weight: 600;
  color: var(--accent-amber); font-family: var(--font-mono);
  text-shadow: 0 0 6px rgba(251,191,36,0.3);
}

.empty-hint {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 40px 0;
}
</style>
