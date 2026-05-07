<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request from '@/utils/request'

const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const loading = ref(false)
const username = ref('')
const email = ref('')
const password = ref('')
const verificationCode = ref('')
const sendingCode = ref(false)
const codeCountdown = ref(0)
const captchaId = ref('')
const captchaCode = ref('')
const captchaSvg = ref('')
let countdownTimer: ReturnType<typeof setInterval> | null = null

function extractApiError(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const loc = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : ''
        return loc ? `${loc}: ${item.msg}` : item.msg
      })
      .filter(Boolean)
      .join('; ') || fallback
  }
  return fallback
}

function startCountdown() {
  codeCountdown.value = 60
  if (countdownTimer) clearInterval(countdownTimer)
  countdownTimer = setInterval(() => {
    codeCountdown.value -= 1
    if (codeCountdown.value <= 0 && countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }
  }, 1000)
}

async function fetchCaptcha() {
  try {
    const { data } = await request.get('/api/auth/captcha')
    captchaId.value = data.captcha_id
    captchaSvg.value = data.svg || data.captcha_svg || ''
    captchaCode.value = ''
  } catch {
    ElMessage.error('Failed to load captcha')
  }
}

async function sendVerificationCode() {
  if (!email.value) {
    ElMessage.warning('Please enter email first')
    return
  }
  sendingCode.value = true
  try {
    await request.post('/api/auth/send-verification-code', { email: email.value })
    ElMessage.success('Verification code sent. Please check your email')
    startCountdown()
  } catch (e: any) {
    ElMessage.error(extractApiError(e, 'Failed to send verification code'))
  } finally {
    sendingCode.value = false
  }
}

async function handleLogin() {
  if (!username.value || !password.value || !captchaCode.value) {
    ElMessage.warning('Please enter username, password and captcha')
    return
  }
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.append('username', username.value)
    params.append('password', password.value)
    const { data } = await request.post('/api/auth/login', params, {
      params: {
        captcha_id: captchaId.value,
        captcha_code: captchaCode.value,
      },
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    ElMessage.success('Login successful')
    router.push('/agent-world')
  } catch (e: any) {
    ElMessage.error(extractApiError(e, 'Login failed'))
    fetchCaptcha()
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  if (!username.value || !email.value || !password.value || !verificationCode.value) {
    ElMessage.warning('Please fill in all required fields')
    return
  }
  loading.value = true
  try {
    const { data } = await request.post('/api/auth/register', {
      username: username.value,
      email: email.value,
      password: password.value,
      verification_code: verificationCode.value,
    })
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    ElMessage.success('Registration successful')
    router.push('/agent-world')
  } catch (e: any) {
    ElMessage.error(extractApiError(e, 'Registration failed'))
  } finally {
    loading.value = false
  }
}

watch(mode, (value) => {
  if (value === 'login' && !captchaSvg.value) fetchCaptcha()
})

onMounted(fetchCaptcha)

onBeforeUnmount(() => {
  if (countdownTimer) clearInterval(countdownTimer)
})
</script>

<template>
  <div class="login-page">
    <div class="bg-layer">
      <div class="grid-bg" />
      <div class="gradient-overlay" />
    </div>

    <div class="login-card">
      <div class="scan-lines" />
      <h1 class="title glow-text">VIRTUAL COMPANY</h1>
      <p class="subtitle">Multi-Agent Career Exploration Simulator</p>

      <div class="tab-bar">
        <button :class="['tab', { active: mode === 'login' }]" @click="mode = 'login'">LOGIN</button>
        <button :class="['tab', { active: mode === 'register' }]" @click="mode = 'register'">REGISTER</button>
      </div>

      <div class="form">
        <div class="field">
          <label>Username</label>
          <input v-model="username" placeholder="Enter username" @keyup.enter="mode === 'login' ? handleLogin() : handleRegister()" />
        </div>

        <div v-if="mode === 'register'" class="field">
          <label>Email</label>
          <input v-model="email" type="email" placeholder="Enter email" />
        </div>

        <div v-if="mode === 'register'" class="field">
          <label>Verification Code</label>
          <div class="inline-field">
            <input v-model="verificationCode" maxlength="6" placeholder="Email code" @keyup.enter="handleRegister()" />
            <button class="mini-btn" :disabled="sendingCode || codeCountdown > 0" @click="sendVerificationCode">
              {{ codeCountdown > 0 ? `${codeCountdown}s` : (sendingCode ? 'Sending' : 'Send') }}
            </button>
          </div>
        </div>

        <div class="field">
          <label>Password</label>
          <input v-model="password" type="password" placeholder="Enter password" @keyup.enter="mode === 'login' ? handleLogin() : handleRegister()" />
        </div>

        <div v-if="mode === 'login'" class="field">
          <label>Captcha</label>
          <div class="captcha-row">
            <input v-model="captchaCode" maxlength="4" placeholder="Code" @keyup.enter="handleLogin()" />
            <button class="captcha-box" type="button" @click="fetchCaptcha" v-html="captchaSvg || 'Refresh'" />
          </div>
        </div>

        <button class="submit-btn" :disabled="loading" @click="mode === 'login' ? handleLogin() : handleRegister()">
          {{ loading ? 'Processing...' : (mode === 'login' ? 'ENTER' : 'CREATE ACCOUNT') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  background: #0a0e17;
  overflow: hidden;
}
.bg-layer { position: absolute; inset: 0; z-index: 0; }
.grid-bg {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(0,255,255,.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,255,255,.03) 1px, transparent 1px);
  background-size: 40px 40px;
}
.gradient-overlay {
  position: absolute; inset: 0;
  background: radial-gradient(ellipse at 50% 30%, rgba(0,255,255,.08) 0%, transparent 60%);
}

.login-card {
  position: relative; z-index: 1;
  width: 420px; padding: 48px 40px;
  background: rgba(10,20,40,.85);
  border: 1px solid rgba(0,255,255,.15);
  border-radius: 16px;
  backdrop-filter: blur(20px);
}
.scan-lines {
  position: absolute; inset: 0; border-radius: 16px; pointer-events: none;
  background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,255,255,.015) 2px, rgba(0,255,255,.015) 4px);
}

.title {
  text-align: center; font-size: 30px; font-weight: 800;
  font-family: 'Orbitron', monospace; letter-spacing: 4px;
  color: #00ffd5; margin: 0 0 4px;
  text-shadow: 0 0 20px rgba(0,255,213,.4);
}
.subtitle {
  text-align: center; font-size: 14px; color: rgba(255,255,255,.4);
  letter-spacing: 2px; margin: 0 0 32px;
}

.tab-bar {
  display: flex; gap: 0; margin-bottom: 28px;
  border: 1px solid rgba(0,255,255,.2); border-radius: 8px; overflow: hidden;
}
.tab {
  flex: 1; padding: 10px; border: none; cursor: pointer;
  font-family: 'Orbitron', monospace; font-size: 15px; letter-spacing: 2px;
  background: transparent; color: rgba(255,255,255,.4); transition: all .2s;
}
.tab.active {
  background: rgba(0,255,255,.1); color: #00ffd5;
  text-shadow: 0 0 10px rgba(0,255,213,.3);
}

.field { margin-bottom: 20px; }
.field label {
  display: block; font-size: 13px; color: rgba(255,255,255,.5);
  letter-spacing: 1px; margin-bottom: 6px; text-transform: uppercase;
}
.field input {
  width: 100%; padding: 12px 16px; box-sizing: border-box;
  background: rgba(0,255,255,.04); border: 1px solid rgba(0,255,255,.15);
  border-radius: 8px; color: #e0e0e0; font-size: 16px; outline: none;
  transition: border-color .2s;
}
.field input:focus { border-color: rgba(0,255,255,.4); }
.field input::placeholder { color: rgba(255,255,255,.2); }

.inline-field,
.captcha-row {
  display: grid;
  grid-template-columns: 1fr 128px;
  gap: 10px;
}

.mini-btn,
.captcha-box {
  min-height: 46px;
  border: 1px solid rgba(0,255,255,.25);
  border-radius: 8px;
  background: rgba(0,255,255,.08);
  color: #00ffd5;
  cursor: pointer;
}

.mini-btn:disabled {
  opacity: .55;
  cursor: not-allowed;
}

.captcha-box {
  padding: 0;
  overflow: hidden;
}

.captcha-box :deep(svg) {
  display: block;
  width: 100%;
  height: 46px;
}

.submit-btn {
  width: 100%; padding: 14px; margin-top: 8px;
  background: linear-gradient(135deg, rgba(0,255,255,.15), rgba(0,255,213,.1));
  border: 1px solid rgba(0,255,255,.3); border-radius: 8px;
  color: #00ffd5; font-family: 'Orbitron', monospace; font-size: 16px;
  letter-spacing: 3px; cursor: pointer; transition: all .2s;
}
.submit-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(0,255,255,.25), rgba(0,255,213,.2));
  box-shadow: 0 0 20px rgba(0,255,255,.15);
}
.submit-btn:disabled { opacity: .5; cursor: not-allowed; }
</style>
