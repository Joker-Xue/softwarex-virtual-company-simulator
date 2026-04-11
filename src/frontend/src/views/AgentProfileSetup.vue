<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAgentWorldStore } from '@/stores/agentWorld'
import { MBTI_TYPES, SELECTABLE_DEPARTMENTS } from '@/constants/companyMap'

const router = useRouter()
const store = useAgentWorldStore()

const nickname = ref('')
const selectedMbti = ref('')
const department = ref('engineering')
const attrs = ref({
  communication: 50,
  leadership: 50,
  creativity: 50,
  technical: 50,
  teamwork: 50,
  diligence: 50,
})

const totalPoints = computed(() =>
  attrs.value.communication + attrs.value.leadership + attrs.value.creativity +
  attrs.value.technical + attrs.value.teamwork + attrs.value.diligence
)
const pointsLeft = computed(() => 300 - totalPoints.value)

const submitting = ref(false)
const showGuide = ref(false)

const mbtiDescriptions: Record<string, string> = {
  INTJ: 'Architect - imaginative and strategic',
  INTP: 'Logician - inventive and analytical',
  ENTJ: 'Commander - bold and decisive leader',
  ENTP: 'Debater - curious and quick-thinking',
  INFJ: 'Advocate - idealistic and insightful',
  INFP: 'Mediator - kind and imaginative',
  ENFJ: 'Protagonist - charismatic and inspiring',
  ENFP: 'Campaigner - energetic and expressive',
  ISTJ: 'Logistician - practical and dependable',
  ISFJ: 'Defender - warm and detail-oriented',
  ESTJ: 'Executive - organized and effective',
  ESFJ: 'Consul - caring and socially attentive',
  ISTP: 'Virtuoso - practical and adaptable',
  ISFP: 'Adventurer - flexible and artistic',
  ESTP: 'Entrepreneur - energetic and action-oriented',
  ESFP: 'Entertainer - spontaneous and lively',
}

// MBTI impact preview data
interface MbtiImpact {
  workStyle: string
  socialStyle: string
  careerTendency: string
  specialBonus: string
}

const mbtiImpacts: Record<string, MbtiImpact> = {
  INTJ: { workStyle: 'Independent problem solving with a focus on elegant solutions', socialStyle: 'Small circles and deep conversations', careerTendency: 'Technical Track', specialBonus: 'High-difficulty task XP +15%' },
  INTP: { workStyle: 'Logic-driven and excited by new ideas', socialStyle: 'Conversation starts with interesting topics', careerTendency: 'Technical Track', specialBonus: 'Work speed +26%' },
  ENTJ: { workStyle: 'Goal-oriented with fast execution', socialStyle: 'Direct, influential, and leadership-heavy', careerTendency: 'Management Track', specialBonus: 'Task XP +5%' },
  ENTP: { workStyle: 'Idea-hopping and innovation-seeking', socialStyle: 'Wide social reach with debate energy', careerTendency: 'Technical Track', specialBonus: 'Social affinity +30%' },
  INFJ: { workStyle: 'Insight-led with a search for meaning', socialStyle: 'Selective but high-quality connection', careerTendency: 'Management Track', specialBonus: 'Work speed +15%' },
  INFP: { workStyle: 'Idealistic with creativity first', socialStyle: 'Gentle, empathic social style', careerTendency: 'Management Track', specialBonus: 'Social affinity +20%' },
  ENFJ: { workStyle: 'Collaborative and motivating', socialStyle: 'Natural organizer of social energy', careerTendency: 'Management Track', specialBonus: 'Social affinity +56%' },
  ENFP: { workStyle: 'Inspiration-driven and multi-threaded', socialStyle: 'Warm, expressive, and highly social', careerTendency: 'Management Track', specialBonus: 'Social affinity +56%' },
  ISTJ: { workStyle: 'Structured, methodical, and process-driven', socialStyle: 'Reliable and steady teammate', careerTendency: 'Technical Track', specialBonus: 'Work speed +27%' },
  ISFJ: { workStyle: 'Careful execution with strong attention to detail', socialStyle: 'Supportive and protective', careerTendency: 'Management Track', specialBonus: 'Work speed +15%' },
  ESTJ: { workStyle: 'Results-first with strong coordination', socialStyle: 'Direct and efficient communication', careerTendency: 'Technical Track', specialBonus: 'Work speed +15%' },
  ESFJ: { workStyle: 'Cooperative and team-centered', socialStyle: 'Community-builder and connector', careerTendency: 'Management Track', specialBonus: 'Social affinity +56%' },
  ISTP: { workStyle: 'Hands-on and focused on real problems', socialStyle: 'Action-oriented and concise', careerTendency: 'Technical Track', specialBonus: 'Work speed +27%' },
  ISFP: { workStyle: 'Creative, aesthetic, and emotionally tuned', socialStyle: 'Quiet observer with gentle presence', careerTendency: 'Management Track', specialBonus: 'Work speed +15%' },
  ESTP: { workStyle: 'Fast-moving and comfortable with risk', socialStyle: 'Energetic and socially bold', careerTendency: 'Technical Track', specialBonus: 'Social affinity +30%' },
  ESFP: { workStyle: 'Adaptive, lively, and atmosphere-driven', socialStyle: 'Mood-maker for the whole team', careerTendency: 'Management Track', specialBonus: 'Social affinity +56%' },
}

const currentImpact = computed(() => selectedMbti.value ? mbtiImpacts[selectedMbti.value] : null)

async function handleSubmit() {
  if (!nickname.value.trim()) {
    ElMessage.warning('Please enter a nickname')
    return
  }
  if (!selectedMbti.value) {
    ElMessage.warning('Please select an MBTI type')
    return
  }
  if (pointsLeft.value < 0) {
    ElMessage.warning('Total attribute points cannot exceed 300')
    return
  }

  submitting.value = true
  try {
    await store.createProfile({
      nickname: nickname.value.trim(),
      mbti: selectedMbti.value,
      department: department.value,
      attr_communication: attrs.value.communication,
      attr_leadership: attrs.value.leadership,
      attr_creativity: attrs.value.creativity,
      attr_technical: attrs.value.technical,
      attr_teamwork: attrs.value.teamwork,
      attr_diligence: attrs.value.diligence,
    })
    showGuide.value = true
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.response?.data?.message || e?.message || 'Unknown error'
    console.error('Failed to create profile:', e?.response?.status, detail, e)
    if (detail.includes('already created')) {
      ElMessage.info('Profile already exists, entering the company...')
      router.push('/agent-world')
    } else {
      ElMessage.error('Creation failed: ' + detail)
    }
  } finally {
    submitting.value = false
  }
}

function enterCompany() {
  showGuide.value = false
  router.push('/agent-world')
}
</script>

<template>
  <div class="agent-setup">
    <!-- Animated grid background -->
    <div class="grid-bg"></div>
    <div class="gradient-overlay"></div>

    <div class="setup-card cyber-card scan-lines">
      <h2 class="setup-title glow-text">AGENT PROFILE SETUP</h2>
      <p class="setup-desc">Start your career inside the virtual company</p>

      <!-- Personality guidance banner -->
      <div class="personality-banner">
        <span class="banner-icon">🧬</span>
        <div class="banner-text">
          <strong>Personality Shapes Destiny</strong>
          <span>The MBTI type you choose determines how your character behaves in the company. Work efficiency, social style, and promotion path are all personality-driven, and the AI runs fully according to this setup.</span>
        </div>
      </div>

      <!-- Nickname -->
      <div class="form-section">
        <label class="form-label">Nickname</label>
        <el-input v-model="nickname" placeholder="Enter your character nickname" maxlength="50" show-word-limit class="cyber-input" />
      </div>

      <!-- Department selection -->
      <div class="form-section">
        <label class="form-label">Select Department</label>
        <div class="dept-grid">
          <div
            v-for="(label, key) in SELECTABLE_DEPARTMENTS"
            :key="key"
            class="dept-card"
            :class="{ active: department === key }"
            @click="department = key"
          >
            <span class="dept-icon">{{ { management:'👑', engineering:'💻', product:'🎯', marketing:'📢', finance:'💰', hr:'👥', operations:'📊', general:'🏢', unassigned:'❓' }[key] || '🏢' }}</span>
            <span class="dept-label-text">{{ label }}</span>
          </div>
        </div>
      </div>

      <!-- MBTI selection -->
      <div class="form-section">
        <label class="form-label">Select MBTI Type</label>
        <div class="mbti-grid">
          <div
            v-for="mbti in MBTI_TYPES"
            :key="mbti"
            class="mbti-card"
            :class="{ active: selectedMbti === mbti }"
            @click="selectedMbti = mbti"
          >
            <div class="mbti-code">{{ mbti }}</div>
            <div class="mbti-desc">{{ mbtiDescriptions[mbti]?.split(' - ')[0] }}</div>
          </div>
        </div>
        <p v-if="selectedMbti" class="mbti-detail">{{ mbtiDescriptions[selectedMbti] }}</p>

        <!-- Personality impact preview -->
        <div v-if="currentImpact" class="impact-preview cyber-card">
          <div class="impact-header glow-text">PERSONALITY IMPACT</div>
          <div class="impact-grid">
            <div class="impact-item">
              <span class="impact-icon">💼</span>
              <div class="impact-content">
                <span class="impact-label">Work Style</span>
                <span class="impact-value">{{ currentImpact.workStyle }}</span>
              </div>
            </div>
            <div class="impact-item">
              <span class="impact-icon">👥</span>
              <div class="impact-content">
                <span class="impact-label">Social Style</span>
                <span class="impact-value">{{ currentImpact.socialStyle }}</span>
              </div>
            </div>
            <div class="impact-item">
              <span class="impact-icon">📈</span>
              <div class="impact-content">
                <span class="impact-label">Growth Track</span>
                <span class="impact-value impact-career">Prefers {{ currentImpact.careerTendency }}</span>
              </div>
            </div>
            <div class="impact-item">
              <span class="impact-icon">⚡</span>
              <div class="impact-content">
                <span class="impact-label">Special Bonus</span>
                <span class="impact-value impact-bonus">{{ currentImpact.specialBonus }}</span>
              </div>
            </div>
          </div>
          <div class="impact-dimensions">
            <div class="dim-item"><span class="dim-letter" :class="{ active: selectedMbti[0] === 'E' }">E Extraversion</span><span class="dim-vs">vs</span><span class="dim-letter" :class="{ active: selectedMbti[0] === 'I' }">I Introversion</span><span class="dim-effect">{{ selectedMbti[0] === 'E' ? 'Higher social frequency with faster affinity growth' : 'More focused on work with higher efficiency' }}</span></div>
            <div class="dim-item"><span class="dim-letter" :class="{ active: selectedMbti[1] === 'S' }">S Sensing</span><span class="dim-vs">vs</span><span class="dim-letter" :class="{ active: selectedMbti[1] === 'N' }">N Intuition</span><span class="dim-effect">{{ selectedMbti[1] === 'S' ? 'Faster at routine tasks' : 'XP bonus on high-difficulty tasks' }}</span></div>
            <div class="dim-item"><span class="dim-letter" :class="{ active: selectedMbti[2] === 'T' }">T Thinking</span><span class="dim-vs">vs</span><span class="dim-letter" :class="{ active: selectedMbti[2] === 'F' }">F Feeling</span><span class="dim-effect">{{ selectedMbti[2] === 'T' ? 'Task XP bonus with a technical-track tendency' : 'Social bonus with a management-track tendency' }}</span></div>
            <div class="dim-item"><span class="dim-letter" :class="{ active: selectedMbti[3] === 'J' }">J Judging</span><span class="dim-vs">vs</span><span class="dim-letter" :class="{ active: selectedMbti[3] === 'P' }">P Perceiving</span><span class="dim-effect">{{ selectedMbti[3] === 'J' ? 'Strict schedule with a higher work ratio' : 'More spontaneous behavior and flexible growth' }}</span></div>
          </div>
        </div>
      </div>

      <!-- Six attributes -->
      <div class="form-section">
        <label class="form-label">
          Allocate Attribute Points
          <span class="points-badge" :class="{ over: pointsLeft < 0, remaining: pointsLeft > 0 }">
            Remaining {{ pointsLeft }} pts
          </span>
        </label>
        <div class="attr-list">
          <div class="attr-row" v-for="(label, key) in { communication: 'Communication', leadership: 'Leadership', creativity: 'Creativity', technical: 'Technical Skill', teamwork: 'Teamwork', diligence: 'Diligence' }" :key="key">
            <span class="attr-label">{{ label }}</span>
            <div class="cyber-slider-track">
              <div class="cyber-slider-fill" :style="{ width: (attrs as any)[key] + '%' }"></div>
              <input
                type="range"
                :min="0" :max="100" :step="5"
                :value="(attrs as any)[key]"
                @input="(e: any) => (attrs as any)[key] = Number(e.target.value)"
                class="cyber-slider-input"
              />
            </div>
            <span class="attr-value">{{ (attrs as any)[key] }}</span>
          </div>
        </div>
      </div>

      <button
        class="cyber-btn submit-btn"
        :class="{ disabled: pointsLeft < 0 || submitting }"
        :disabled="pointsLeft < 0 || submitting"
        @click="handleSubmit"
      >
        <span v-if="submitting" class="btn-loading"></span>
        <span>Create Profile and Enter the Company</span>
      </button>
    </div>

    <!-- Welcome Guide Modal -->
    <Teleport to="body">
      <Transition name="guide-fade">
        <div v-if="showGuide" class="guide-overlay" @click.self="enterCompany">
          <div class="guide-modal">
            <!-- Decorative top beam -->
            <div class="guide-beam"></div>

            <!-- Header -->
            <div class="guide-header">
              <div class="guide-icon-ring">
                <span class="guide-icon">🚀</span>
              </div>
              <h2 class="guide-title">Welcome to the Virtual Company!</h2>
              <p class="guide-subtitle">Your AI workplace simulation is about to begin</p>
            </div>

            <!-- Content -->
            <div class="guide-body">
              <div class="guide-item">
                <span class="gi-icon">🧬</span>
                <div class="gi-text">
                  <strong>Personality Drives Everything</strong>
                  <span>Your MBTI setup shapes the entire simulation: work speed, social choices, task preference, and promotion track are all decided by the AI through personality rules.</span>
                </div>
              </div>
              <div class="guide-item">
                <span class="gi-icon">🤖</span>
                <div class="gi-text">
                  <strong>Fully Autonomous AI</strong>
                  <span>Your character will work, socialize, join events, complete tasks, and gain experience automatically. You can simply observe how each decision emerges from the personality model.</span>
                </div>
              </div>
              <div class="guide-item">
                <span class="gi-icon">📈</span>
                <div class="gi-text">
                  <strong>From Intern to CEO</strong>
                  <span>You start as an intern and climb through automatic promotion by completing tasks. At Level 4, the AI chooses a technical or management track based on your T/F dimension.</span>
                </div>
              </div>
              <div class="guide-item">
                <span class="gi-icon">📊</span>
                <div class="gi-text">
                  <strong>Transparent Decision Trace</strong>
                  <span>Every decision includes MBTI factor breakdowns. Open the trace panel to inspect why the AI picked a specific behavior, task, or event in real time.</span>
                </div>
              </div>
              <div class="guide-item">
                <span class="gi-icon">⚡</span>
                <div class="gi-text">
                  <strong>Fast-Forward Observation</strong>
                  <span>Need a faster view? Use the top-bar simulation speed switch to move between 1x, 2x, and 5x while watching the character grow through the company.</span>
                </div>
              </div>
            </div>

            <!-- MBTI summary for this character -->
            <div class="guide-mbti-bar">
              <span class="gmb-type">{{ selectedMbti }}</span>
              <span class="gmb-sep">·</span>
              <span class="gmb-info" v-if="currentImpact">{{ currentImpact.workStyle }}</span>
              <span class="gmb-sep">·</span>
              <span class="gmb-career" v-if="currentImpact">{{ currentImpact.careerTendency }}</span>
            </div>

            <!-- Enter button -->
            <button class="guide-enter-btn" @click="enterCompany">
              <span>Enter the Virtual Company</span>
              <span class="enter-arrow">→</span>
            </button>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* ═══ Page Background ═══ */
.agent-setup {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 40px 24px;
  background: var(--bg-deep);
  position: relative;
  overflow: hidden;
}

/* Animated gradient overlay */
.gradient-overlay {
  position: fixed;
  inset: 0;
  background: linear-gradient(
    135deg,
    rgba(10, 14, 26, 0.95) 0%,
    rgba(30, 10, 60, 0.8) 50%,
    rgba(10, 14, 26, 0.95) 100%
  );
  background-size: 200% 200%;
  animation: gradient-shift 12s ease-in-out infinite;
  pointer-events: none;
  z-index: 0;
}

@keyframes gradient-shift {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

/* Grid pattern background */
.grid-bg {
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(34, 211, 238, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(34, 211, 238, 0.04) 1px, transparent 1px);
  background-size: 40px 40px;
  pointer-events: none;
  z-index: 0;
  animation: grid-move 20s linear infinite;
}

@keyframes grid-move {
  0% { transform: translate(0, 0); }
  100% { transform: translate(40px, 40px); }
}

/* ═══ Main Card ═══ */
.setup-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 720px;
  padding: 36px;
  margin-top: 20px;
  animation: cyber-fade-in 0.5s var(--ease-out-expo) both;
}

@keyframes cyber-fade-in {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ═══ Title ═══ */
.setup-title {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 3px;
  text-transform: uppercase;
  margin: 0 0 6px;
}
.setup-desc {
  color: var(--text-secondary);
  font-family: var(--font-body);
  font-size: 14px;
  margin: 0 0 28px;
}

/* ═══ Personality Banner ═══ */
.personality-banner {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 18px;
  margin-bottom: 28px;
  background: linear-gradient(135deg, rgba(167, 139, 250, 0.08), rgba(34, 211, 238, 0.08));
  border: 1px solid rgba(167, 139, 250, 0.25);
  border-radius: var(--radius-md);
  animation: banner-glow 3s ease-in-out infinite alternate;
}
@keyframes banner-glow {
  0% { box-shadow: 0 0 8px rgba(167, 139, 250, 0.1); }
  100% { box-shadow: 0 0 20px rgba(167, 139, 250, 0.2); }
}
.banner-icon { font-size: 22px; flex-shrink: 0; margin-top: 2px; }
.banner-text { display: flex; flex-direction: column; gap: 4px; }
.banner-text strong {
  font-family: var(--font-body);
  font-size: 14px;
  color: var(--accent-violet);
  text-shadow: 0 0 8px rgba(167, 139, 250, 0.4);
}
.banner-text span {
  font-family: var(--font-body);
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

/* ═══ Impact Preview Card ═══ */
.impact-preview {
  margin-top: 16px;
  padding: 16px 18px;
}
.impact-header {
  font-family: var(--font-display);
  font-size: 12px;
  letter-spacing: 2px;
  margin-bottom: 14px;
  text-transform: uppercase;
}
.impact-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}
.impact-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.impact-icon { font-size: 18px; flex-shrink: 0; }
.impact-content { display: flex; flex-direction: column; gap: 2px; }
.impact-label { font-size: 10px; color: var(--text-muted); font-family: var(--font-body); text-transform: uppercase; letter-spacing: 0.5px; }
.impact-value { font-size: 13px; color: var(--text-primary); font-family: var(--font-body); }
.impact-career { color: var(--accent-emerald); font-weight: 600; }
.impact-bonus { color: var(--accent-amber); font-weight: 600; text-shadow: 0 0 6px rgba(251, 191, 36, 0.3); }

/* ═══ Dimension Explanations ═══ */
.impact-dimensions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border-dim);
}
.dim-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}
.dim-letter {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(100, 116, 139, 0.1);
  transition: all var(--duration-base) ease;
}
.dim-letter.active {
  color: var(--accent-cyan);
  background: rgba(34, 211, 238, 0.1);
  border: 1px solid rgba(34, 211, 238, 0.3);
  text-shadow: 0 0 6px rgba(34, 211, 238, 0.4);
}
.dim-vs { color: var(--text-muted); font-size: 9px; }
.dim-effect { color: var(--text-secondary); font-family: var(--font-body); margin-left: auto; font-size: 11px; }

/* ═══ Form Sections ═══ */
.form-section {
  margin-bottom: 28px;
}
.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-body);
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 12px;
}

/* ═══ Input Override ═══ */
.cyber-input :deep(.el-input__wrapper) {
  background: rgba(17, 24, 39, 0.8);
  border: 1px solid var(--border-glow);
  border-radius: var(--radius-sm);
  box-shadow: none;
  color: var(--text-primary);
  transition: border-color var(--duration-base) ease;
}
.cyber-input :deep(.el-input__wrapper:hover),
.cyber-input :deep(.el-input__wrapper.is-focus) {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 10px rgba(34, 211, 238, 0.1);
}
.cyber-input :deep(.el-input__inner) {
  color: var(--text-primary);
  font-family: var(--font-body);
}
.cyber-input :deep(.el-input__inner::placeholder) {
  color: var(--text-muted);
}
.cyber-input :deep(.el-input__count-inner) {
  background: transparent;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
}

/* ═══ Department Grid ═══ */
.dept-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.dept-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 14px 8px;
  background: rgba(17, 24, 39, 0.5);
  border: 1px solid var(--border-dim);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-base) ease;
}
.dept-card:hover {
  border-color: rgba(34, 211, 238, 0.3);
  background: rgba(34, 211, 238, 0.04);
}
.dept-card.active {
  border-color: var(--accent-cyan);
  background: rgba(34, 211, 238, 0.1);
  box-shadow: 0 0 16px rgba(34, 211, 238, 0.15), inset 0 0 16px rgba(34, 211, 238, 0.05);
}
.dept-icon {
  font-size: 26px;
}
.dept-label-text {
  font-family: var(--font-body);
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}
.dept-card.active .dept-label-text {
  color: var(--accent-cyan);
}

/* ═══ MBTI Grid ═══ */
.mbti-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.mbti-card {
  text-align: center;
  padding: 12px 6px;
  background: rgba(17, 24, 39, 0.6);
  border: 1px solid var(--border-dim);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-base) ease;
}
.mbti-card:hover {
  border-color: rgba(34, 211, 238, 0.25);
  background: rgba(34, 211, 238, 0.04);
}
.mbti-card.active {
  border-color: var(--accent-cyan);
  background: rgba(34, 211, 238, 0.08);
  box-shadow: 0 0 12px rgba(34, 211, 238, 0.15);
}
.mbti-code {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 15px;
  color: var(--text-primary);
  letter-spacing: 1px;
}
.mbti-card.active .mbti-code {
  color: var(--accent-cyan);
  text-shadow: 0 0 8px rgba(34, 211, 238, 0.4);
}
.mbti-desc {
  font-family: var(--font-body);
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 3px;
}
.mbti-detail {
  margin-top: 10px;
  padding: 10px 14px;
  background: rgba(34, 211, 238, 0.05);
  border: 1px solid var(--border-dim);
  border-left: 3px solid var(--accent-cyan);
  border-radius: var(--radius-sm);
  font-family: var(--font-body);
  font-size: 13px;
  color: var(--text-secondary);
}

/* ═══ Points Badge ═══ */
.points-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 10px;
  font-weight: 600;
  letter-spacing: 0.5px;
  border: 1px solid;
  transition: all var(--duration-base) ease;
}
.points-badge.remaining {
  color: var(--accent-amber);
  border-color: rgba(251, 191, 36, 0.3);
  background: rgba(251, 191, 36, 0.08);
  text-shadow: 0 0 6px rgba(251, 191, 36, 0.3);
}
.points-badge.over {
  color: var(--accent-rose);
  border-color: rgba(251, 113, 133, 0.3);
  background: rgba(251, 113, 133, 0.08);
  text-shadow: 0 0 6px rgba(251, 113, 133, 0.3);
  animation: cyber-pulse 1.5s ease-in-out infinite;
}

@keyframes cyber-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* ═══ Custom Neon Sliders ═══ */
.attr-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.attr-row {
  display: flex;
  align-items: center;
  gap: 14px;
}
.attr-label {
  width: 56px;
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  flex-shrink: 0;
}
.attr-value {
  width: 36px;
  text-align: right;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 13px;
  color: var(--accent-cyan);
  text-shadow: 0 0 6px rgba(34, 211, 238, 0.3);
}

/* Neon slider track */
.cyber-slider-track {
  flex: 1;
  position: relative;
  height: 8px;
  background: rgba(34, 211, 238, 0.08);
  border-radius: 4px;
  overflow: visible;
}
.cyber-slider-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--accent-cyan), var(--accent-violet));
  box-shadow: 0 0 10px rgba(34, 211, 238, 0.3);
  transition: width 0.1s ease;
  pointer-events: none;
}
.cyber-slider-input {
  position: absolute;
  top: 50%;
  left: 0;
  width: 100%;
  transform: translateY(-50%);
  -webkit-appearance: none;
  appearance: none;
  background: transparent;
  cursor: pointer;
  margin: 0;
  height: 20px;
}
.cyber-slider-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--accent-cyan);
  border: 2px solid var(--bg-deep);
  box-shadow: 0 0 8px rgba(34, 211, 238, 0.5);
  cursor: pointer;
  transition: box-shadow var(--duration-base) ease;
}
.cyber-slider-input::-webkit-slider-thumb:hover {
  box-shadow: 0 0 14px rgba(34, 211, 238, 0.7);
}
.cyber-slider-input::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--accent-cyan);
  border: 2px solid var(--bg-deep);
  box-shadow: 0 0 8px rgba(34, 211, 238, 0.5);
  cursor: pointer;
}

/* ═══ Submit Button ═══ */
.submit-btn {
  width: 100%;
  margin-top: 12px;
  padding: 14px 32px;
  font-size: 14px;
  font-family: var(--font-display);
  letter-spacing: 2px;
  text-transform: uppercase;
}
.submit-btn.disabled {
  opacity: 0.4;
  cursor: not-allowed;
  pointer-events: none;
}
.btn-loading {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid transparent;
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  margin-right: 8px;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ═══ Welcome Guide Modal ═══ */
.guide-fade-enter-active { transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
.guide-fade-leave-active { transition: all 0.25s ease-in; }
.guide-fade-enter-from { opacity: 0; }
.guide-fade-leave-to { opacity: 0; }
.guide-fade-enter-from .guide-modal { transform: scale(0.9) translateY(20px); }
.guide-fade-leave-to .guide-modal { transform: scale(0.95) translateY(10px); }

.guide-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(2, 6, 18, 0.85);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  padding: 24px;
}

.guide-modal {
  position: relative;
  width: 100%;
  max-width: 520px;
  max-height: 85vh;
  overflow-y: auto;
  background: linear-gradient(165deg, rgba(15, 23, 42, 0.97), rgba(10, 14, 30, 0.99));
  border: 1px solid rgba(34, 211, 238, 0.2);
  border-radius: 16px;
  padding: 0 28px 28px;
  box-shadow:
    0 0 40px rgba(34, 211, 238, 0.08),
    0 0 80px rgba(167, 139, 250, 0.06),
    0 25px 50px rgba(0, 0, 0, 0.5);
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.guide-modal::-webkit-scrollbar { width: 3px; }
.guide-modal::-webkit-scrollbar-thumb { background: rgba(34, 211, 238, 0.15); border-radius: 2px; }

/* Top decorative beam */
.guide-beam {
  height: 3px;
  margin: 0 -28px 24px;
  border-radius: 0 0 4px 4px;
  background: linear-gradient(90deg, transparent, var(--accent-cyan, #22d3ee) 20%, var(--accent-violet, #a78bfa) 50%, var(--accent-cyan, #22d3ee) 80%, transparent);
  opacity: 0.7;
}

/* Header */
.guide-header {
  text-align: center;
  margin-bottom: 24px;
}
.guide-icon-ring {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: rgba(34, 211, 238, 0.08);
  border: 2px solid rgba(34, 211, 238, 0.25);
  margin-bottom: 12px;
  animation: icon-pulse 2.5s ease-in-out infinite;
}
@keyframes icon-pulse {
  0%, 100% { box-shadow: 0 0 12px rgba(34, 211, 238, 0.15); }
  50% { box-shadow: 0 0 24px rgba(34, 211, 238, 0.3), 0 0 48px rgba(167, 139, 250, 0.1); }
}
.guide-icon { font-size: 26px; }
.guide-title {
  font-family: var(--font-display, 'Orbitron', sans-serif);
  font-size: 20px;
  font-weight: 700;
  color: var(--accent-cyan, #22d3ee);
  letter-spacing: 1.5px;
  margin: 0 0 6px;
  text-shadow: 0 0 12px rgba(34, 211, 238, 0.4);
}
.guide-subtitle {
  font-family: var(--font-body, 'Noto Sans SC', sans-serif);
  font-size: 13px;
  color: var(--text-secondary, #94a3b8);
  margin: 0;
}

/* Body items */
.guide-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 20px;
}
.guide-item {
  display: flex;
  gap: 12px;
  padding: 12px 14px;
  background: rgba(17, 24, 39, 0.6);
  border: 1px solid rgba(34, 211, 238, 0.08);
  border-left: 3px solid rgba(34, 211, 238, 0.3);
  border-radius: 8px;
  transition: border-color 0.3s ease, background 0.3s ease;
}
.guide-item:hover {
  border-left-color: var(--accent-cyan, #22d3ee);
  background: rgba(34, 211, 238, 0.04);
}
.gi-icon {
  font-size: 20px;
  flex-shrink: 0;
  margin-top: 1px;
}
.gi-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.gi-text strong {
  font-family: var(--font-body, 'Noto Sans SC', sans-serif);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
}
.gi-text span {
  font-family: var(--font-body, 'Noto Sans SC', sans-serif);
  font-size: 12px;
  color: var(--text-muted, #64748b);
  line-height: 1.5;
}

/* MBTI summary bar */
.guide-mbti-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 16px;
  margin-bottom: 20px;
  background: rgba(167, 139, 250, 0.06);
  border: 1px solid rgba(167, 139, 250, 0.15);
  border-radius: 8px;
}
.gmb-type {
  font-family: var(--font-display, 'Orbitron', sans-serif);
  font-size: 14px;
  font-weight: 700;
  color: var(--accent-violet, #a78bfa);
  letter-spacing: 1px;
  text-shadow: 0 0 8px rgba(167, 139, 250, 0.4);
}
.gmb-sep {
  color: rgba(100, 116, 139, 0.4);
  font-size: 10px;
}
.gmb-info {
  font-family: var(--font-body, 'Noto Sans SC', sans-serif);
  font-size: 12px;
  color: var(--text-secondary, #94a3b8);
}
.gmb-career {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-emerald, #34d399);
  padding: 1px 8px;
  background: rgba(52, 211, 153, 0.08);
  border: 1px solid rgba(52, 211, 153, 0.2);
  border-radius: 4px;
}

/* Enter button */
.guide-enter-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 14px 32px;
  font-family: var(--font-display, 'Orbitron', sans-serif);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--bg-deep, #0a0e1a);
  background: linear-gradient(135deg, var(--accent-cyan, #22d3ee), var(--accent-violet, #a78bfa));
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 20px rgba(34, 211, 238, 0.25);
}
.guide-enter-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 28px rgba(34, 211, 238, 0.35), 0 0 12px rgba(167, 139, 250, 0.2);
}
.guide-enter-btn:active {
  transform: translateY(0);
}
.enter-arrow {
  font-size: 18px;
  transition: transform 0.3s ease;
}
.guide-enter-btn:hover .enter-arrow {
  transform: translateX(4px);
}
</style>
