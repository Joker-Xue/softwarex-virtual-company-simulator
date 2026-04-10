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
  INTJ: '建筑师 - 富有想象力的战略家',
  INTP: '逻辑学家 - 创新的发明家',
  ENTJ: '指挥官 - 大胆的领导者',
  ENTP: '辩论家 - 聪明好奇的思想家',
  INFJ: '提倡者 - 安静而神秘的理想主义者',
  INFP: '调停者 - 诗意善良的利他主义者',
  ENFJ: '主人公 - 富有魅力的鼓舞者',
  ENFP: '竞选者 - 热情有Creativity的社交达人',
  ISTJ: '物流师 - 务实可靠的人',
  ISFJ: '守卫者 - 专注而温暖的守护者',
  ESTJ: '总经理 - 出色的管理者',
  ESFJ: '执政官 - 极有同情心的社交者',
  ISTP: '鉴赏家 - 大胆而实际的实验家',
  ISFP: '探险家 - 灵活有魅力的艺术家',
  ESTP: '企业家 - 聪明精力充沛的人',
  ESFP: '表演者 - 自发热情的娱乐者',
}

// MBTI性格影响预览数据
interface MbtiImpact {
  workStyle: string
  socialStyle: string
  careerTendency: string
  specialBonus: string
}

const mbtiImpacts: Record<string, MbtiImpact> = {
  INTJ: { workStyle: '独立思考，追求完美方案', socialStyle: '少而精，深度交流', careerTendency: '技术路线', specialBonus: '高难度任务XP +15%' },
  INTP: { workStyle: '逻辑驱动，热衷创新', socialStyle: '话题驱动型社交', careerTendency: '技术路线', specialBonus: '工作效率 +26%' },
  ENTJ: { workStyle: '目标导向，高效执行', socialStyle: '主导型社交，影响力强', careerTendency: '管理路线', specialBonus: '任务XP +5%' },
  ENTP: { workStyle: '跳跃思维，善于创新', socialStyle: '广泛社交，辩论爱好者', careerTendency: '技术路线', specialBonus: '社交亲密度 +30%' },
  INFJ: { workStyle: '洞察驱动，追求意义', socialStyle: '选择性社交，高质量', careerTendency: '管理路线', specialBonus: '工作效率 +15%' },
  INFP: { workStyle: '理想主义，创意优先', socialStyle: '温和共情型社交', careerTendency: '管理路线', specialBonus: '社交亲密度 +20%' },
  ENFJ: { workStyle: '团队协作，激励他人', socialStyle: '天生的社交组织者', careerTendency: '管理路线', specialBonus: '社交亲密度 +56%' },
  ENFP: { workStyle: '灵感驱动，多项目并行', socialStyle: '热情洋溢的社交达人', careerTendency: '管理路线', specialBonus: '社交亲密度 +56%' },
  ISTJ: { workStyle: '严谨有序，按流程办事', socialStyle: '守信可靠的合作者', careerTendency: '技术路线', specialBonus: '工作效率 +27%' },
  ISFJ: { workStyle: '细致入微，关注细节', socialStyle: '温暖守护型社交', careerTendency: '管理路线', specialBonus: '工作效率 +15%' },
  ESTJ: { workStyle: '结果导向，管理力强', socialStyle: '直接高效的沟通风格', careerTendency: '技术路线', specialBonus: '工作效率 +15%' },
  ESFJ: { workStyle: '协调合作，关注团队', socialStyle: '社区核心型社交', careerTendency: '管理路线', specialBonus: '社交亲密度 +56%' },
  ISTP: { workStyle: '实操派，解决实际问题', socialStyle: '行动导向型社交', careerTendency: '技术路线', specialBonus: '工作效率 +27%' },
  ISFP: { workStyle: '感性创作，艺术导向', socialStyle: '安静的观察者', careerTendency: '管理路线', specialBonus: '工作效率 +15%' },
  ESTP: { workStyle: '行动派，敢于冒险', socialStyle: '活力四射的社交者', careerTendency: '技术路线', specialBonus: '社交亲密度 +30%' },
  ESFP: { workStyle: '活泼多变，氛围担当', socialStyle: '团队开心果', careerTendency: '管理路线', specialBonus: '社交亲密度 +56%' },
}

const currentImpact = computed(() => selectedMbti.value ? mbtiImpacts[selectedMbti.value] : null)

async function handleSubmit() {
  if (!nickname.value.trim()) {
    ElMessage.warning('请输入Nickname')
    return
  }
  if (!selectedMbti.value) {
    ElMessage.warning('Please select MBTI type')
    return
  }
  if (pointsLeft.value < 0) {
    ElMessage.warning('属性总点数不能超过300')
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
    const detail = e?.response?.data?.detail || e?.response?.data?.message || e?.message || '未知错误'
    console.error('Create Character失败:', e?.response?.status, detail, e)
    if (detail.includes('已创建')) {
      ElMessage.info('角色已存在，正在进入公司...')
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
      <p class="setup-desc">在虚拟公司中开启你的职业生涯</p>

      <!-- 性格核心提示横幅 -->
      <div class="personality-banner">
        <span class="banner-icon">🧬</span>
        <div class="banner-text">
          <strong>性格决定命运</strong>
          <span>你选择的MBTI将决定角色在公司中的一切表现 —— 工作效率、社交方式、晋升路线全部由性格驱动，AI将完全基于你的性格设定自主运行。</span>
        </div>
      </div>

      <!-- Nickname -->
      <div class="form-section">
        <label class="form-label">Nickname</label>
        <el-input v-model="nickname" placeholder="输入你的角色Nickname" maxlength="50" show-word-limit class="cyber-input" />
      </div>

      <!-- Department选择 -->
      <div class="form-section">
        <label class="form-label">选择Department</label>
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

      <!-- MBTI选择 -->
      <div class="form-section">
        <label class="form-label">选择 MBTI 类型</label>
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

        <!-- 性格影响预览卡片 -->
        <div v-if="currentImpact" class="impact-preview cyber-card">
          <div class="impact-header glow-text">PERSONALITY IMPACT</div>
          <div class="impact-grid">
            <div class="impact-item">
              <span class="impact-icon">💼</span>
              <div class="impact-content">
                <span class="impact-label">工作风格</span>
                <span class="impact-value">{{ currentImpact.workStyle }}</span>
              </div>
            </div>
            <div class="impact-item">
              <span class="impact-icon">👥</span>
              <div class="impact-content">
                <span class="impact-label">社交倾向</span>
                <span class="impact-value">{{ currentImpact.socialStyle }}</span>
              </div>
            </div>
            <div class="impact-item">
              <span class="impact-icon">📈</span>
              <div class="impact-content">
                <span class="impact-label">成长路线</span>
                <span class="impact-value impact-career">倾向{{ currentImpact.careerTendency }}</span>
              </div>
            </div>
            <div class="impact-item">
              <span class="impact-icon">⚡</span>
              <div class="impact-content">
                <span class="impact-label">特殊加成</span>
                <span class="impact-value impact-bonus">{{ currentImpact.specialBonus }}</span>
              </div>
            </div>
          </div>
          <div class="impact-dimensions">
            <div class="dim-item"><span class="dim-letter" :class="{ active: selectedMbti[0] === 'E' }">E 外向</span><span class="dim-vs">vs</span><span class="dim-letter" :class="{ active: selectedMbti[0] === 'I' }">I 内向</span><span class="dim-effect">{{ selectedMbti[0] === 'E' ? '社交频率高，亲密度增长快' : '专注工作，效率更高' }}</span></div>
            <div class="dim-item"><span class="dim-letter" :class="{ active: selectedMbti[1] === 'S' }">S 实感</span><span class="dim-vs">vs</span><span class="dim-letter" :class="{ active: selectedMbti[1] === 'N' }">N 直觉</span><span class="dim-effect">{{ selectedMbti[1] === 'S' ? '常规任务完成快' : '高难度任务XP加成' }}</span></div>
            <div class="dim-item"><span class="dim-letter" :class="{ active: selectedMbti[2] === 'T' }">T 思考</span><span class="dim-vs">vs</span><span class="dim-letter" :class="{ active: selectedMbti[2] === 'F' }">F 情感</span><span class="dim-effect">{{ selectedMbti[2] === 'T' ? '任务XP加成，倾向技术路线' : '社交加成，倾向管理路线' }}</span></div>
            <div class="dim-item"><span class="dim-letter" :class="{ active: selectedMbti[3] === 'J' }">J 判断</span><span class="dim-vs">vs</span><span class="dim-letter" :class="{ active: selectedMbti[3] === 'P' }">P 感知</span><span class="dim-effect">{{ selectedMbti[3] === 'J' ? '日程严格，工作占比高' : '行为随机，灵活发展' }}</span></div>
          </div>
        </div>
      </div>

      <!-- 六维属性 -->
      <div class="form-section">
        <label class="form-label">
          分配属性点
          <span class="points-badge" :class="{ over: pointsLeft < 0, remaining: pointsLeft > 0 }">
            剩余 {{ pointsLeft }} 点
          </span>
        </label>
        <div class="attr-list">
          <div class="attr-row" v-for="(label, key) in { communication: 'Communication', leadership: 'Leadership', creativity: 'Creativity', technical: 'Technical', teamwork: 'Teamwork', diligence: '勤奋度' }" :key="key">
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
        <span>Create Character，进入公司</span>
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
              <h2 class="guide-title">欢迎加入虚拟公司！</h2>
              <p class="guide-subtitle">你的AI职场模拟之旅即将开始</p>
            </div>

            <!-- Content -->
            <div class="guide-body">
              <div class="guide-item">
                <span class="gi-icon">🧬</span>
                <div class="gi-text">
                  <strong>性格驱动一切</strong>
                  <span>你设定的MBTI性格将全面决定角色行为 —— 工作效率、社交选择、任务偏好、晋升路线，全部由AI根据你的性格自主决策。</span>
                </div>
              </div>
              <div class="guide-item">
                <span class="gi-icon">🤖</span>
                <div class="gi-text">
                  <strong>AI全自动运行</strong>
                  <span>你的角色将自主工作、社交、参加活动、完成任务并获得经验。你只需观察AI如何基于你的性格做出每一个决定。</span>
                </div>
              </div>
              <div class="guide-item">
                <span class="gi-icon">📈</span>
                <div class="gi-text">
                  <strong>从实习生到CEO</strong>
                  <span>起步于实习生，通过完成任务积累经验自动晋升。到达Lv.4时AI会根据你的T/F维度自动选择技术或管理路线。</span>
                </div>
              </div>
              <div class="guide-item">
                <span class="gi-icon">📊</span>
                <div class="gi-text">
                  <strong>透明决策轨迹</strong>
                  <span>每一个决策都附带MBTI因素分解。打开「轨迹」面板，实时查看AI为什么选择了这个行为、这个任务、这个活动。</span>
                </div>
              </div>
              <div class="guide-item">
                <span class="gi-icon">⚡</span>
                <div class="gi-text">
                  <strong>加速观察</strong>
                  <span>觉得太慢？顶栏模拟速度可切换1x/2x/5x，加速观察你的角色在公司中的成长轨迹！</span>
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
              <span>进入虚拟公司</span>
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
