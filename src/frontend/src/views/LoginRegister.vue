<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request from '@/utils/request'

const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const loading = ref(false)
const username = ref('')
const email = ref('')
const password = ref('')

async function handleLogin() {
  if (!username.value || !password.value) {
    ElMessage.warning('Please enter username and password')
    return
  }
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.append('username', username.value)
    params.append('password', password.value)
    const { data } = await request.post('/api/auth/login', params)
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    ElMessage.success('Login successful')
    router.push('/agent-world')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || 'Login failed')
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  if (!username.value || !email.value || !password.value) {
    ElMessage.warning('Please fill in all required fields')
    return
  }
  loading.value = true
  try {
    const { data } = await request.post('/api/auth/register', {
      username: username.value,
      email: email.value,
      password: password.value,
    })
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    ElMessage.success('Registration successful')
    router.push('/agent-world')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || 'Registration failed')
  } finally {
    loading.value = false
  }
}
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

        <div class="field">
          <label>Password</label>
          <input v-model="password" type="password" placeholder="Enter password" @keyup.enter="mode === 'login' ? handleLogin() : handleRegister()" />
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
  text-align: center; font-size: 28px; font-weight: 800;
  font-family: 'Orbitron', monospace; letter-spacing: 4px;
  color: #00ffd5; margin: 0 0 4px;
  text-shadow: 0 0 20px rgba(0,255,213,.4);
}
.subtitle {
  text-align: center; font-size: 12px; color: rgba(255,255,255,.4);
  letter-spacing: 2px; margin: 0 0 32px;
}

.tab-bar {
  display: flex; gap: 0; margin-bottom: 28px;
  border: 1px solid rgba(0,255,255,.2); border-radius: 8px; overflow: hidden;
}
.tab {
  flex: 1; padding: 10px; border: none; cursor: pointer;
  font-family: 'Orbitron', monospace; font-size: 13px; letter-spacing: 2px;
  background: transparent; color: rgba(255,255,255,.4); transition: all .2s;
}
.tab.active {
  background: rgba(0,255,255,.1); color: #00ffd5;
  text-shadow: 0 0 10px rgba(0,255,213,.3);
}

.field { margin-bottom: 20px; }
.field label {
  display: block; font-size: 11px; color: rgba(255,255,255,.5);
  letter-spacing: 1px; margin-bottom: 6px; text-transform: uppercase;
}
.field input {
  width: 100%; padding: 12px 16px; box-sizing: border-box;
  background: rgba(0,255,255,.04); border: 1px solid rgba(0,255,255,.15);
  border-radius: 8px; color: #e0e0e0; font-size: 14px; outline: none;
  transition: border-color .2s;
}
.field input:focus { border-color: rgba(0,255,255,.4); }
.field input::placeholder { color: rgba(255,255,255,.2); }

.submit-btn {
  width: 100%; padding: 14px; margin-top: 8px;
  background: linear-gradient(135deg, rgba(0,255,255,.15), rgba(0,255,213,.1));
  border: 1px solid rgba(0,255,255,.3); border-radius: 8px;
  color: #00ffd5; font-family: 'Orbitron', monospace; font-size: 14px;
  letter-spacing: 3px; cursor: pointer; transition: all .2s;
}
.submit-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(0,255,255,.25), rgba(0,255,213,.2));
  box-shadow: 0 0 20px rgba(0,255,255,.15);
}
.submit-btn:disabled { opacity: .5; cursor: not-allowed; }
</style>
