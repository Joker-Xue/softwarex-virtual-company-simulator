<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { AVATAR_COLORS, ACTION_LABELS } from '@/constants/companyMap'
import { useAgentWorldStore } from '@/stores/agentWorld'
import type { CompanyRoom, AgentProfile, RoomInteractions, ObjectAction, ObjectOccupancy } from '@/stores/agentWorld'
import { FLOOR_Y_OFFSET } from '@/constants/companyMap'

const props = defineProps<{
  room: CompanyRoom | null
  agents: AgentProfile[]
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const store = useAgentWorldStore()
const canvasRef = ref<HTMLCanvasElement | null>(null)
const loading = ref(false)
const statusText = ref('')
const interactions = ref<RoomInteractions | null>(null)
let ctx: CanvasRenderingContext2D | null = null
let animFrame = 0

const INTERIOR_WIDTH = 500
const INTERIOR_HEIGHT = 400

const OBJECT_COLORS: Record<string, string> = {
  desk: '#1a1f2e',
  chair: '#151a28',
  computer: '#0f1520',
  plant: '#0d1a14',
  whiteboard: '#111827',
  coffee_machine: '#1a1520',
  table: '#1a1820',
  sofa: '#150d28',
  filing_cabinet: '#141820',
  bookshelf: '#151018',
  safe: '#111418',
  server_rack: '#0a0e18',
  water_cooler: '#0d1520',
  water_fountain: '#0d1518',
  info_board: '#1a1810',
  notice_board: '#1a1810',
  interview_booth: '#150d20',
  projector_screen: '#0f1520',
  presentation_screen: '#0f1320',
  mood_board: '#1a0d18',
  printer: '#141820',
  vending_machine: '#0d1818',
  bar_counter: '#1a1510',
  globe: '#0d1520',
  calculator_station: '#141618',
}

const ROOM_FLOOR_COLORS: Record<string, string> = {
  ceo_office: '#0f1729',
  office: '#0f1729',
  meeting: '#0f1729',
  lounge: '#0f1729',
  cafeteria: '#0f1729',
}

const scaleX = computed(() => {
  if (!props.room) return 1
  return INTERIOR_WIDTH / props.room.width
})
const scaleY = computed(() => {
  if (!props.room) return 1
  return INTERIOR_HEIGHT / props.room.height
})

const roomAgents = computed(() => {
  if (!props.room) return []
  const r = props.room
  return props.agents.filter(a =>
    a.pos_x >= r.x && a.pos_x <= r.x + r.width &&
    (a.pos_y % FLOOR_Y_OFFSET) >= r.y && (a.pos_y % FLOOR_Y_OFFSET) <= r.y + r.height &&
    Math.floor(a.pos_y / FLOOR_Y_OFFSET) + 1 === r.floor,
  )
})

let glowPhase = 0

function getObjectColor(type: string): string {
  return OBJECT_COLORS[type] || '#94a3b8'
}

function getOccupancyByKey(objectKey: string): ObjectOccupancy | undefined {
  return interactions.value?.occupancies.find(o => o.object_key === objectKey)
}

function getActionByKey(objectKey: string): ObjectAction | undefined {
  return interactions.value?.object_actions.find(a => a.object_key === objectKey)
}

function draw() {
  if (!ctx || !canvasRef.value || !props.room) return

  const room = props.room
  ctx.clearRect(0, 0, INTERIOR_WIDTH, INTERIOR_HEIGHT)
  ctx.fillStyle = ROOM_FLOOR_COLORS[room.room_type] || '#0f1729'
  ctx.fillRect(0, 0, INTERIOR_WIDTH, INTERIOR_HEIGHT)

  ctx.strokeStyle = 'rgba(34,211,238,0.05)'
  ctx.lineWidth = 0.5
  for (let x = 0; x < INTERIOR_WIDTH; x += 50) {
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, INTERIOR_HEIGHT)
    ctx.stroke()
  }
  for (let y = 0; y < INTERIOR_HEIGHT; y += 50) {
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(INTERIOR_WIDTH, y)
    ctx.stroke()
  }

  const wallGrad = ctx.createLinearGradient(0, 0, 0, INTERIOR_HEIGHT)
  wallGrad.addColorStop(0, 'rgba(34,211,238,0.12)')
  wallGrad.addColorStop(0.05, 'rgba(34,211,238,0.02)')
  wallGrad.addColorStop(1, 'transparent')
  ctx.fillStyle = wallGrad
  ctx.fillRect(0, 0, INTERIOR_WIDTH, INTERIOR_HEIGHT)
  ctx.strokeStyle = 'rgba(34,211,238,0.3)'
  ctx.lineWidth = 2
  ctx.strokeRect(1, 1, INTERIOR_WIDTH - 2, INTERIOR_HEIGHT - 2)

  ctx.fillStyle = 'rgba(10,14,26,0.7)'
  ctx.fillRect(0, 0, INTERIOR_WIDTH, 28)
  ctx.save()
  ctx.shadowColor = '#22d3ee'
  ctx.shadowBlur = 4
  ctx.fillStyle = '#22d3ee'
  ctx.font = 'bold 14px "Orbitron", sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText(room.name + ' - ' + (room.description || ''), INTERIOR_WIDTH / 2, 19)
  ctx.restore()

  glowPhase += 0.05
  const glowIntensity = Math.sin(glowPhase) * 0.3 + 0.5

  const objects = room.interior_objects || []
  const sx = scaleX.value
  const sy = scaleY.value

  for (let idx = 0; idx < objects.length; idx++) {
    const obj = objects[idx]
    const ox = obj.x * sx
    const oy = obj.y * sy
    const ow = obj.width * sx
    const oh = obj.height * sy
    const color = getObjectColor(obj.type)

    ctx.fillStyle = color
    ctx.fillRect(ox, oy, ow, oh)

    const objectKey = `obj_${idx}`
    const action = getActionByKey(objectKey)
    const occupancy = getOccupancyByKey(objectKey)
    const isInteractive = !!action
    const isOccupied = !!occupancy?.occupant_agent_id && occupancy.occupant_agent_id !== store.myProfile?.id

    if (isInteractive) {
      ctx.save()
      ctx.shadowColor = isOccupied ? '#f97316' : '#22d3ee'
      ctx.shadowBlur = 4 + glowIntensity * 8
      ctx.strokeStyle = isOccupied
        ? `rgba(249,115,22,${0.5 + glowIntensity * 0.3})`
        : `rgba(34,211,238,${0.4 + glowIntensity * 0.3})`
      ctx.lineWidth = 1.5
      ctx.strokeRect(ox, oy, ow, oh)
      ctx.restore()
      if (occupancy && occupancy.queue_count > 0) {
        ctx.fillStyle = '#f97316'
        ctx.font = 'bold 10px sans-serif'
        ctx.fillText(`排队 ${occupancy.queue_count}`, ox + ow - 18, oy + 14)
      }
    } else {
      ctx.strokeStyle = 'rgba(167,139,250,0.25)'
      ctx.lineWidth = 1
      ctx.strokeRect(ox, oy, ow, oh)
    }

    ctx.fillStyle = 'rgba(226,232,240,0.7)'
    ctx.font = '10px sans-serif'
    ctx.textAlign = 'center'
    const labelY = oy + oh + 12
    if (labelY < INTERIOR_HEIGHT - 4) {
      ctx.fillText(obj.name, ox + ow / 2, labelY)
    } else {
      ctx.fillText(obj.name, ox + ow / 2, oy - 4)
    }

    if (isInteractive) {
      ctx.save()
      ctx.shadowColor = '#22d3ee'
      ctx.shadowBlur = 4
      ctx.fillStyle = `rgba(34,211,238,${glowIntensity})`
      ctx.beginPath()
      ctx.arc(ox + ow - 4, oy + 4, 3, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
    }
  }

  for (const agent of roomAgents.value) {
    const ax = (agent.pos_x - room.x) * sx
    const ay = ((agent.pos_y % FLOOR_Y_OFFSET) - room.y) * sy
    const acolor = AVATAR_COLORS[agent.avatar_key] || '#6366f1'

    ctx.save()
    ctx.shadowColor = acolor
    ctx.shadowBlur = 10
    ctx.beginPath()
    ctx.arc(ax, ay, 16, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(10,14,26,0.6)'
    ctx.fill()
    ctx.strokeStyle = acolor
    ctx.lineWidth = 2
    ctx.stroke()
    ctx.restore()

    ctx.fillStyle = '#e2e8f0'
    ctx.font = 'bold 13px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(agent.nickname[0], ax, ay + 5)

    const actionLabel = ACTION_LABELS[agent.current_action] || ''
    if (actionLabel && agent.current_action !== 'idle') {
      const tw = ctx.measureText(actionLabel).width + 8
      ctx.fillStyle = 'rgba(10,14,26,0.85)'
      ctx.beginPath()
      ctx.roundRect(ax - tw / 2, ay + 20, tw, 16, 4)
      ctx.fill()
      ctx.strokeStyle = 'rgba(34,211,238,0.4)'
      ctx.lineWidth = 0.8
      ctx.stroke()
      ctx.fillStyle = '#e2e8f0'
      ctx.font = '10px sans-serif'
      ctx.fillText(actionLabel, ax, ay + 31)
    }
  }

  drawLegend()
  animFrame = requestAnimationFrame(draw)
}

function drawLegend() {
  if (!ctx) return
  const legendY = INTERIOR_HEIGHT - 20
  ctx.fillStyle = 'rgba(10,14,26,0.85)'
  ctx.fillRect(0, legendY - 8, INTERIOR_WIDTH, 28)
  ctx.strokeStyle = 'rgba(34,211,238,0.15)'
  ctx.lineWidth = 0.5
  ctx.beginPath()
  ctx.moveTo(0, legendY - 8)
  ctx.lineTo(INTERIOR_WIDTH, legendY - 8)
  ctx.stroke()

  ctx.font = '9px sans-serif'
  ctx.textAlign = 'left'
  ctx.fillStyle = 'rgba(226,232,240,0.6)'
  ctx.fillText('点击空白移动到合法点位；点击高亮物件执行操作', 10, legendY + 6)
}

function startDrawLoop() {
  if (!canvasRef.value) return
  ctx = canvasRef.value.getContext('2d')
  if (ctx) {
    glowPhase = 0
    animFrame = requestAnimationFrame(draw)
  }
}

function stopDrawLoop() {
  cancelAnimationFrame(animFrame)
  animFrame = 0
}

async function loadInteractions() {
  if (!props.room) return
  loading.value = true
  try {
    interactions.value = await store.fetchRoomInteractions(props.room.id)
  } catch (e: any) {
    interactions.value = null
    statusText.value = '交互结构加载失败'
    ElMessage.error(e?.response?.data?.message || '房间交互加载失败')
  } finally {
    loading.value = false
  }
}

function pointerToRoomPos(evt: MouseEvent): { roomX: number; roomY: number } | null {
  if (!canvasRef.value || !props.room) return null
  const rect = canvasRef.value.getBoundingClientRect()
  const px = (evt.clientX - rect.left) * (INTERIOR_WIDTH / rect.width)
  const py = (evt.clientY - rect.top) * (INTERIOR_HEIGHT / rect.height)
  return {
    roomX: Math.round(px / scaleX.value),
    roomY: Math.round(py / scaleY.value),
  }
}

function hitInteractiveObject(roomX: number, roomY: number): string | null {
  const objs = props.room?.interior_objects || []
  for (let idx = objs.length - 1; idx >= 0; idx--) {
    const obj = objs[idx]
    if (!(obj.interactive && getActionByKey(`obj_${idx}`))) continue
    if (
      roomX >= obj.x && roomX <= obj.x + obj.width &&
      roomY >= obj.y && roomY <= obj.y + obj.height
    ) {
      return `obj_${idx}`
    }
  }
  return null
}

async function onCanvasClick(evt: MouseEvent) {
  if (!props.room || loading.value || !store.myProfile) return
  const p = pointerToRoomPos(evt)
  if (!p) return
  const objectKey = hitInteractiveObject(p.roomX, p.roomY)

  try {
    if (objectKey) {
      loading.value = true
      const result = await store.interactInsideRoom(props.room.id, objectKey)
      statusText.value = result.reason
      if (result.success) {
        ElMessage.success(`操作成功：任务+${result.task_delta}，XP+${result.xp_delta}`)
        await Promise.all([store.fetchTasks(), loadInteractions()])
      } else {
        ElMessage.warning(result.reason)
        await loadInteractions()
      }
      return
    }

    loading.value = true
    await store.moveInsideRoom(props.room.id, p.roomX, p.roomY)
    statusText.value = '已移动到最近可交互点位'
  } catch (e: any) {
    statusText.value = e?.response?.data?.message || '操作失败'
    ElMessage.error(statusText.value)
  } finally {
    loading.value = false
  }
}

watch(() => props.visible, async (val) => {
  if (val) {
    await loadInteractions()
    setTimeout(() => startDrawLoop(), 50)
  } else {
    stopDrawLoop()
    statusText.value = ''
    interactions.value = null
  }
})

watch(() => props.room?.id, async () => {
  if (props.visible) {
    await loadInteractions()
    stopDrawLoop()
    setTimeout(() => startDrawLoop(), 50)
  }
})

onMounted(async () => {
  if (props.visible) {
    await loadInteractions()
    setTimeout(() => startDrawLoop(), 50)
  }
})

onUnmounted(() => {
  stopDrawLoop()
})
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="room ? room.name + ' - 内部场景' : '房间内部'"
    width="560px"
    :close-on-click-modal="true"
    @close="emit('close')"
  >
    <div class="room-interior-wrap" v-loading="loading">
      <canvas
        ref="canvasRef"
        :width="500"
        :height="400"
        class="room-interior-canvas"
        @click="onCanvasClick"
      />
      <div class="room-info" v-if="room">
        <span class="info-item">容量: {{ room.capacity }}人</span>
        <span class="info-item">物品: {{ (room.interior_objects || []).length }}件</span>
        <span class="info-item">在场: {{ roomAgents.length }}人</span>
      </div>
      <div v-if="statusText" class="status-line">{{ statusText }}</div>
    </div>
  </el-dialog>
</template>

<style scoped>
.room-interior-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.room-interior-canvas {
  border: 1px solid rgba(34,211,238,0.2);
  border-radius: 8px;
  background: #0a0e1a;
  max-width: 100%;
  height: auto;
  box-shadow: 0 0 16px rgba(34,211,238,0.08);
  cursor: crosshair;
}
.room-info {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: rgba(226,232,240,0.7);
}
.info-item {
  background: rgba(17,24,39,0.9);
  border: 1px solid rgba(34,211,238,0.2);
  padding: 4px 10px;
  border-radius: 6px;
}
.status-line {
  width: 100%;
  text-align: center;
  color: #22d3ee;
  font-size: 12px;
  border-top: 1px dashed rgba(34,211,238,0.25);
  padding-top: 8px;
}
</style>
