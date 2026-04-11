<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{ level: number; title: string }>()
const emit = defineEmits<{ close: [] }>()
const show = ref(true)

onMounted(() => {
  setTimeout(() => {
    show.value = false
    emit('close')
  }, 4000)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="promo">
      <div v-if="show" class="promotion-overlay" @click="show = false; emit('close')">
        <div class="promotion-modal cyber-card breathe scan-lines">
          <div class="promo-icon">&#x1F680;</div>
          <div class="promo-title glow-text">Congratulations on the promotion！</div>
          <div class="promo-level glow-text-amber">{{ title }}</div>
          <div class="promo-level-number">Lv.{{ level }}</div>
          <div class="promo-desc">You have been promoted to <span class="glow-text-violet">Lv.{{ level }} {{ title }}</span></div>
          <div class="fireworks">
            <span v-for="i in 12" :key="i" class="spark" :style="{ '--i': i }" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.promotion-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.85);
  cursor: pointer;
  backdrop-filter: blur(4px);
}
.promotion-modal {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: 40px 48px;
  text-align: center;
  color: var(--text-primary);
  position: relative;
  overflow: hidden;
  animation: promo-pop-in 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
  border-color: rgba(34, 211, 238, 0.3);
  box-shadow:
    0 0 40px rgba(34, 211, 238, 0.15),
    0 0 80px rgba(167, 139, 250, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
}
.promo-icon {
  font-size: 56px;
  margin-bottom: 8px;
  filter: drop-shadow(0 0 12px rgba(34, 211, 238, 0.5));
}
.promo-title {
  font-size: 28px;
  font-weight: 800;
  font-family: var(--font-display);
  letter-spacing: 2px;
}
.promo-level {
  font-size: 36px;
  font-weight: 900;
  font-family: var(--font-display);
  margin: 8px 0 4px;
}
.promo-level-number {
  font-size: 48px;
  font-weight: 900;
  font-family: var(--font-mono);
  color: var(--accent-amber);
  text-shadow: 0 0 20px rgba(251, 191, 36, 0.6), 0 0 40px rgba(251, 191, 36, 0.3);
  margin: 4px 0 12px;
}
.promo-desc {
  font-size: 16px;
  font-family: var(--font-body);
  color: var(--text-secondary);
}

.fireworks {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.spark {
  position: absolute;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  top: 50%;
  left: 50%;
  animation: spark-fly 1.2s ease-out forwards;
  animation-delay: calc(var(--i) * 0.06s);
}
/* Multi-color neon sparks */
.spark:nth-child(3n+1) {
  background: var(--accent-cyan);
  box-shadow: 0 0 6px var(--accent-cyan);
}
.spark:nth-child(3n+2) {
  background: var(--accent-violet);
  box-shadow: 0 0 6px var(--accent-violet);
}
.spark:nth-child(3n+3) {
  background: var(--accent-emerald);
  box-shadow: 0 0 6px var(--accent-emerald);
}
.spark:nth-child(4n) {
  background: var(--accent-amber);
  box-shadow: 0 0 6px var(--accent-amber);
}

@keyframes spark-fly {
  0% {
    transform: translate(0, 0) scale(1);
    opacity: 1;
  }
  100% {
    transform: translate(
      calc(cos(calc(var(--i) * 30deg)) * 140px),
      calc(sin(calc(var(--i) * 30deg)) * 140px)
    ) scale(0);
    opacity: 0;
  }
}
@keyframes promo-pop-in {
  0% {
    transform: scale(0.8) rotate(-2deg);
    opacity: 0;
  }
  100% {
    transform: scale(1) rotate(0deg);
    opacity: 1;
  }
}

.promo-enter-active { transition: opacity 0.3s; }
.promo-leave-active { transition: opacity 0.3s; }
.promo-enter-from, .promo-leave-to { opacity: 0; }
</style>
