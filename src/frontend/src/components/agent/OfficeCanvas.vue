<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAgentWorldStore } from '@/stores/agentWorld'
import { CANVAS_WIDTH, CANVAS_HEIGHT, AVATAR_COLORS, ACTION_LABELS, FLOOR_LABELS, getRoomsByFloor, ROOM_FURNITURE, ROOM_ICONS, FLOOR_Y_OFFSET, NAMED_SPOTS, SPOT_COLORS } from '@/constants/companyMap'
import type { RoomConfig, FurnitureItem } from '@/constants/companyMap'
import { drawSprite, drawNameLabel, drawActionBubble } from '@/utils/spriteRenderer'
import type { SpriteOptions } from '@/utils/spriteRenderer'

const store = useAgentWorldStore()
const canvasRef = ref<HTMLCanvasElement | null>(null)
let ctx: CanvasRenderingContext2D | null = null
let animFrame = 0
let hoveredRoom = ''

// ---- Off-screen static canvas ----
let staticCanvas: HTMLCanvasElement | null = null
let staticCtx: CanvasRenderingContext2D | null = null
let staticDirty = true
let lastFloor = -1

// ---- Frame rate throttling ----
let lastDrawTime = 0
const TARGET_FPS = 30
const FRAME_INTERVAL = 1000 / TARGET_FPS

// Floor-filtered rooms
const currentRooms = computed(() => getRoomsByFloor(store.currentFloor))
const floorKeys = computed(() => Object.keys(FLOOR_LABELS).map(Number))

type VisualRoomConfig = RoomConfig & { sourceRoom: RoomConfig }

const FLOOR_VIEWPORTS: Record<number, {
  source: { x: number; y: number; width: number; height: number }
  target: { x: number; y: number; width: number; height: number }
}> = {
  2: {
    source: { x: 20, y: 60, width: 520, height: 280 },
    target: { x: 30, y: 58, width: 410, height: 430 },
  },
}

const emit = defineEmits<{
  (e: 'enter-room', room: any): void
}>()

// ---- Animation state ----

/** Smoothly interpolated display positions for each agent. */
const displayPositions = new Map<number, { x: number; y: number }>()

/** Previous-frame positions used to detect movement and compute direction. */
const prevPositions = new Map<number, { x: number; y: number }>()

/** Per-agent walk-animation frame counter (only advances while moving). */
const walkFrames = new Map<number, number>()

/** Global tick counter, incremented every draw(). */
let tickCounter = 0

/** Frames an agent must be still before we consider them stopped. */
const STOP_THRESHOLD = 3
/** Per-agent stillness counter. */
const stillCounters = new Map<number, number>()

/** Linear interpolation factor per frame (~10 %). */
const LERP_SPEED = 0.10

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

/**
 * Determine facing direction from a movement delta.
 * Prefers the axis with the larger absolute change; defaults to 'down'.
 */
function directionFromDelta(dx: number, dy: number): SpriteOptions['direction'] {
  if (Math.abs(dx) < 0.3 && Math.abs(dy) < 0.3) return 'down'
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx > 0 ? 'right' : 'left'
  }
  return dy > 0 ? 'down' : 'up'
}

// ---- Draw loop ----

/**
 * Draw static elements to off-screen canvas（floor、grid、Room）
 * Redraw only when staticDirty is true
 */
/** Draw a single furniture item inside a room */
function drawFurniture(c: CanvasRenderingContext2D, room: RoomConfig, item: FurnitureItem) {
  const fx = room.x + room.width * item.rx
  const fy = room.y + 30 + (room.height - 30) * item.ry  // offset 30 for label area

  c.save()
  switch (item.type) {
    case 'desk': {
      // Desk top — dark surface with neon outline
      c.fillStyle = '#1a1f2e'
      c.beginPath()
      c.roundRect(fx - 14, fy - 6, 28, 12, 2)
      c.fill()
      c.strokeStyle = 'rgba(34,211,238,0.4)'
      c.lineWidth = 0.8
      c.stroke()
      // Monitor — glowing screen
      c.fillStyle = '#0a0e1a'
      c.fillRect(fx - 5, fy - 12, 10, 7)
      c.fillStyle = '#22d3ee'
      c.fillRect(fx - 4, fy - 11, 8, 5)
      break
    }
    case 'chair': {
      c.fillStyle = '#1e2536'
      c.beginPath()
      c.arc(fx, fy, 5, 0, Math.PI * 2)
      c.fill()
      c.strokeStyle = 'rgba(167,139,250,0.4)'
      c.lineWidth = 0.6
      c.stroke()
      c.fillStyle = '#151a28'
      c.fillRect(fx - 3, fy + 3, 6, 3)
      break
    }
    case 'plant': {
      // Pot — dark with neon edge
      c.fillStyle = '#1a1f2e'
      c.fillRect(fx - 4, fy + 2, 8, 6)
      // Leaves — neon green glow
      c.fillStyle = 'rgba(52,211,153,0.7)'
      c.beginPath()
      c.arc(fx, fy - 2, 6, 0, Math.PI * 2)
      c.fill()
      c.fillStyle = 'rgba(52,211,153,0.5)'
      c.beginPath()
      c.arc(fx - 2, fy, 4, 0, Math.PI * 2)
      c.fill()
      break
    }
    case 'sofa': {
      c.fillStyle = '#1a1040'
      c.beginPath()
      c.roundRect(fx - 16, fy - 5, 32, 10, 4)
      c.fill()
      c.strokeStyle = 'rgba(167,139,250,0.5)'
      c.lineWidth = 0.8
      c.stroke()
      // Armrests
      c.fillStyle = '#150d35'
      c.beginPath()
      c.roundRect(fx - 18, fy - 6, 6, 12, 3)
      c.fill()
      c.beginPath()
      c.roundRect(fx + 12, fy - 6, 6, 12, 3)
      c.fill()
      break
    }
    case 'table': {
      c.fillStyle = '#1a1f2e'
      c.beginPath()
      c.roundRect(fx - 12, fy - 8, 24, 16, 3)
      c.fill()
      c.strokeStyle = 'rgba(34,211,238,0.3)'
      c.lineWidth = 0.8
      c.stroke()
      break
    }
    case 'screen': {
      // Projector screen — dark with neon border
      c.fillStyle = '#0f1520'
      c.fillRect(fx - 20, fy - 6, 40, 24)
      c.strokeStyle = 'rgba(34,211,238,0.6)'
      c.lineWidth = 1
      c.strokeRect(fx - 20, fy - 6, 40, 24)
      // Scanline effect
      c.fillStyle = 'rgba(34,211,238,0.08)'
      for (let sy = fy - 5; sy < fy + 17; sy += 3) {
        c.fillRect(fx - 19, sy, 38, 1)
      }
      // Stand
      c.fillStyle = '#1e2536'
      c.fillRect(fx - 1, fy - 10, 2, 4)
      break
    }
    case 'bookshelf': {
      c.fillStyle = '#151a28'
      c.fillRect(fx - 6, fy - 10, 12, 20)
      c.strokeStyle = 'rgba(167,139,250,0.3)'
      c.lineWidth = 0.6
      c.strokeRect(fx - 6, fy - 10, 12, 20)
      // Books — neon colored spines
      const bookColors = ['rgba(251,113,133,0.7)', 'rgba(96,165,250,0.7)', 'rgba(52,211,153,0.7)', 'rgba(251,191,36,0.7)', 'rgba(167,139,250,0.7)']
      for (let i = 0; i < 4; i++) {
        c.fillStyle = bookColors[i % bookColors.length]
        c.fillRect(fx - 4, fy - 8 + i * 5, 8, 4)
      }
      break
    }
    case 'coffee_machine': {
      c.fillStyle = '#1a1f2e'
      c.beginPath()
      c.roundRect(fx - 6, fy - 8, 12, 16, 2)
      c.fill()
      c.strokeStyle = 'rgba(34,211,238,0.3)'
      c.lineWidth = 0.6
      c.stroke()
      // Cup — neon amber
      c.fillStyle = 'rgba(251,191,36,0.6)'
      c.fillRect(fx - 3, fy + 4, 6, 5)
      // Steam — neon vapor
      c.strokeStyle = 'rgba(34,211,238,0.3)'
      c.lineWidth = 1
      c.beginPath()
      c.moveTo(fx - 1, fy - 10)
      c.quadraticCurveTo(fx - 3, fy - 14, fx, fy - 16)
      c.stroke()
      c.beginPath()
      c.moveTo(fx + 1, fy - 10)
      c.quadraticCurveTo(fx + 3, fy - 14, fx, fy - 17)
      c.stroke()
      break
    }
  }
  c.restore()
}

/** Draw all named spots for the current floor as glowing dot indicators */
function drawNamedSpots(c: CanvasRenderingContext2D, floor: number) {
  for (const [, spot] of Object.entries(NAMED_SPOTS)) {
    if (spot.floor !== floor) continue
    const color = SPOT_COLORS[spot.spot_type]
    const visualPoint = toVisualPoint(spot.x, spot.y)
    const x = visualPoint.x
    const y = visualPoint.y

    c.save()

    // Anchor spots (CEO/Director desks): larger star/diamond indicator
    if (spot.spot_type === 'anchor') {
      c.shadowColor = color
      c.shadowBlur = 10
      // Diamond shape
      c.beginPath()
      c.moveTo(x, y - 5)
      c.lineTo(x + 4, y)
      c.lineTo(x, y + 5)
      c.lineTo(x - 4, y)
      c.closePath()
      c.fillStyle = color
      c.fill()
      c.strokeStyle = '#fff'
      c.lineWidth = 0.6
      c.stroke()
    } else {
      // Regular spots: small glowing dot
      const radius = spot.spot_type === 'meeting' ? 2.5 : 2
      c.shadowColor = color
      c.shadowBlur = 6
      c.beginPath()
      c.arc(x, y, radius, 0, Math.PI * 2)
      c.fillStyle = color + '99'  // semi-transparent fill
      c.fill()
      c.strokeStyle = color
      c.lineWidth = 0.8
      c.stroke()
    }

    c.restore()
  }
}

function drawFittedText(
  c: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
) {
  if (maxWidth <= 0) return
  if (c.measureText(text).width <= maxWidth) {
    c.fillText(text, x, y)
    return
  }
  let fitted = text
  while (fitted.length > 1 && c.measureText(fitted + '...').width > maxWidth) {
    fitted = fitted.slice(0, -1)
  }
  c.fillText(fitted.length > 1 ? fitted + '...' : text.slice(0, 1), x, y)
}

function compactRoomName(name: string) {
  const compactNames: Record<string, string> = {
    Engineering: 'Eng',
    Marketing: 'Mktg',
    Operations: 'Ops',
    'HR Department': 'HR',
  }
  return compactNames[name] || name
}

function getFloorViewport() {
  return FLOOR_VIEWPORTS[store.currentFloor]
}

function toVisualPoint(x: number, y: number): { x: number; y: number } {
  const viewport = getFloorViewport()
  if (!viewport) return { x, y }
  const sx = viewport.target.width / viewport.source.width
  const sy = viewport.target.height / viewport.source.height
  return {
    x: viewport.target.x + (x - viewport.source.x) * sx,
    y: viewport.target.y + (y - viewport.source.y) * sy,
  }
}

function fromVisualPoint(x: number, y: number): { x: number; y: number } {
  const viewport = getFloorViewport()
  if (!viewport) return { x, y }
  const sx = viewport.source.width / viewport.target.width
  const sy = viewport.source.height / viewport.target.height
  return {
    x: viewport.source.x + (x - viewport.target.x) * sx,
    y: viewport.source.y + (y - viewport.target.y) * sy,
  }
}

function toVisualRoom(room: RoomConfig): VisualRoomConfig {
  const topLeft = toVisualPoint(room.x, room.y)
  const bottomRight = toVisualPoint(room.x + room.width, room.y + room.height)
  return {
    ...room,
    x: topLeft.x,
    y: topLeft.y,
    width: bottomRight.x - topLeft.x,
    height: bottomRight.y - topLeft.y,
    sourceRoom: room,
  }
}

function currentVisualRooms(): VisualRoomConfig[] {
  return currentRooms.value.map(toVisualRoom)
}

function drawStatic() {
  if (!staticCtx || !staticCanvas) return
  const c = staticCtx
  const w = staticCanvas.width
  const h = staticCanvas.height
  c.clearRect(0, 0, w, h)

  // ── Background: cyberpunk dark grid floor ──
  const bgGradient = c.createLinearGradient(0, 0, w, h)
  bgGradient.addColorStop(0, '#0a0e1a')
  bgGradient.addColorStop(0.5, '#111827')
  bgGradient.addColorStop(1, '#0f172a')
  c.fillStyle = bgGradient
  c.fillRect(0, 0, w, h)

  // Grid lines
  c.strokeStyle = 'rgba(34,211,238,0.08)'
  c.lineWidth = 0.5
  for (let gx = 0; gx <= w; gx += 30) {
    c.beginPath()
    c.moveTo(gx, 0)
    c.lineTo(gx, h)
    c.stroke()
  }
  for (let gy = 0; gy <= h; gy += 30) {
    c.beginPath()
    c.moveTo(0, gy)
    c.lineTo(w, gy)
    c.stroke()
  }
  // Major grid lines
  c.strokeStyle = 'rgba(167,139,250,0.12)'
  c.lineWidth = 1
  for (let gx = 0; gx <= w; gx += 150) {
    c.beginPath()
    c.moveTo(gx, 0)
    c.lineTo(gx, h)
    c.stroke()
  }
  for (let gy = 0; gy <= h; gy += 150) {
    c.beginPath()
    c.moveTo(0, gy)
    c.lineTo(w, gy)
    c.stroke()
  }

  // Floor label
  c.fillStyle = 'rgba(34,211,238,0.08)'
  c.font = 'bold 48px "Orbitron", sans-serif'
  c.textAlign = 'center'
  c.fillText(FLOOR_LABELS[store.currentFloor] || `${store.currentFloor}F`, w / 2, 42)

  // ── Draw rooms ──
  for (const sourceRoom of currentRooms.value) {
    const room = toVisualRoom(sourceRoom)
    const rx = room.x
    const ry = room.y
    const rw = room.width
    const rh = room.height

    // Room shadow/glow
    c.save()
    c.shadowColor = room.labelColor
    c.shadowBlur = 12
    c.fillStyle = 'rgba(17,24,39,0.75)'
    c.beginPath()
    c.roundRect(rx, ry, rw, rh, 8)
    c.fill()
    c.restore()

    // Room background
    const roomGradient = c.createLinearGradient(rx, ry, rx, ry + rh)
    roomGradient.addColorStop(0, 'rgba(30,41,59,0.9)')
    roomGradient.addColorStop(1, 'rgba(15,23,42,0.85)')
    c.fillStyle = roomGradient
    c.beginPath()
    c.roundRect(rx, ry, rw, rh, 8)
    c.fill()

    // Room border
    c.strokeStyle = room.labelColor
    c.lineWidth = 2
    c.shadowColor = room.labelColor
    c.shadowBlur = 8
    c.stroke()
    c.shadowBlur = 0

    // Header area
    c.fillStyle = darkenHex(room.labelColor, 0.65)
    c.globalAlpha = 0.35
    c.beginPath()
    c.roundRect(rx + 2, ry + 2, rw - 4, 30, [6, 6, 0, 0])
    c.fill()
    c.globalAlpha = 1

    // Room icon and label
    c.fillStyle = room.labelColor
    c.font = '16px sans-serif'
    c.textAlign = 'left'
    c.textBaseline = 'middle'
    c.fillText(ROOM_ICONS[room.type] || '□', rx + 12, ry + 17)

    const compactHeader = rw < 145
    c.fillStyle = '#f1f5f9'
    c.font = `${compactHeader ? 'bold 13px' : 'bold 14px'} "Microsoft YaHei", sans-serif`
    drawFittedText(c, compactHeader ? compactRoomName(room.name) : room.name, rx + 36, ry + 17, Math.max(20, rw - (compactHeader ? 48 : 98)))

    // Department tag
    if (!compactHeader) {
      c.fillStyle = 'rgba(148,163,184,0.7)'
      c.font = '10px "JetBrains Mono", monospace'
      c.textAlign = 'right'
      drawFittedText(c, room.department.toUpperCase(), rx + rw - 10, ry + 18, Math.max(24, rw - 52))
    }

    // Door indicator (bottom center)
    const doorW = 20
    const doorX = rx + rw / 2 - doorW / 2
    c.fillStyle = '#0a0e1a'
    c.fillRect(doorX, ry + rh - 4, doorW, 4)
    c.strokeStyle = 'rgba(34,211,238,0.6)'
    c.lineWidth = 1
    c.strokeRect(doorX, ry + rh - 4, doorW, 4)

    // Furniture
    const furnitureList = ROOM_FURNITURE[sourceRoom.type] || []
    for (const item of furnitureList) {
      drawFurniture(c, room, item)
    }
  }

  // ── Corridor decorations (small neon plants/lights) ──
  const plantPositions = [
    { x: 300, y: 42 }, { x: 300, y: 558 },
    { x: 42, y: 300 }, { x: 558, y: 300 },
  ]
  for (const p of plantPositions) {
    c.save()
    c.shadowColor = '#34d399'
    c.shadowBlur = 8
    c.fillStyle = 'rgba(52,211,153,0.6)'
    c.beginPath()
    c.arc(p.x, p.y, 4, 0, Math.PI * 2)
    c.fill()
    c.restore()
  }

  // ── Named spot indicators ──
  drawNamedSpots(c, store.currentFloor)

  // ── Spot legend (bottom-right corner) ──
  const legendItems: Array<{ label: string; color: string }> = [
    { label: 'Anchor', color: SPOT_COLORS.anchor },
    { label: 'Desk', color: SPOT_COLORS.work },
    { label: 'Visitor', color: SPOT_COLORS.visitor },
    { label: 'Rest', color: SPOT_COLORS.rest },
    { label: 'Meeting', color: SPOT_COLORS.meeting },
  ]
  const legendFontSize = 15
  const legendLineH = 23
  c.font = `600 ${legendFontSize}px "Microsoft YaHei", sans-serif`
  const legendPaddingX = 15
  const legendPaddingY = 13
  const legendDotGap = 17
  const legendTextW = Math.ceil(Math.max(...legendItems.map(item => c.measureText(item.label).width)))
  const legendW = Math.max(138, legendPaddingX * 2 + legendDotGap + legendTextW)
  const legendH = legendPaddingY * 2 + legendItems.length * legendLineH
  const legendBoxX = w - legendW - 12
  const legendX = legendBoxX + legendPaddingX
  const legendStartY = h - legendH + legendPaddingY - 12
  c.fillStyle = 'rgba(10,14,26,0.7)'
  c.beginPath()
  c.roundRect(legendBoxX, legendStartY - legendPaddingY, legendW, legendH, 8)
  c.fill()
  c.shadowColor = '#22d3ee'
  c.shadowBlur = 8
  c.strokeStyle = 'rgba(34,211,238,0.35)'
  c.lineWidth = 1.4
  c.stroke()
  c.shadowBlur = 0
  for (let i = 0; i < legendItems.length; i++) {
    const ly = legendStartY + i * legendLineH
    c.fillStyle = legendItems[i].color
    c.shadowColor = legendItems[i].color
    c.shadowBlur = 6
    c.beginPath()
    c.arc(legendX, ly + 1, 4.5, 0, Math.PI * 2)
    c.fill()
    c.shadowBlur = 0
    c.fillStyle = 'rgba(226,232,240,0.8)'
    c.textAlign = 'left'
    c.textBaseline = 'middle'
    drawFittedText(c, legendItems[i].label, legendX + 13, ly + 1, legendW - legendPaddingX * 2 - legendDotGap)
  }

  staticDirty = false
}

/** Darken a hex color for map rendering */
function darkenHex(hex: string, amount: number): string {
  const raw = hex.replace('#', '')
  const num = parseInt(raw, 16)
  const r = Math.max(0, Math.floor(((num >> 16) & 0xff) * (1 - amount)))
  const g = Math.max(0, Math.floor(((num >> 8) & 0xff) * (1 - amount)))
  const b = Math.max(0, Math.floor((num & 0xff) * (1 - amount)))
  return `rgb(${r},${g},${b})`
}

function draw() {
  if (!ctx || !canvasRef.value) return

  // Frame rate throttling
  const now = performance.now()
  if (now - lastDrawTime < FRAME_INTERVAL) {
    animFrame = requestAnimationFrame(draw)
    return
  }
  lastDrawTime = now

  const w = canvasRef.value.width
  const h = canvasRef.value.height
  ctx.clearRect(0, 0, w, h)
  tickCounter++

  // DetectionFloor changes，mark static layer needs to be redrawn
  if (store.currentFloor !== lastFloor) {
    staticDirty = true
    lastFloor = store.currentFloor
  }

  // Draw static layer（Off-screen canvas）
  if (staticDirty) {
    drawStatic()
  }
  if (staticCanvas) {
    ctx.drawImage(staticCanvas, 0, 0)
  }

  // Draw a hover highlight（dynamic，follow mouse）— neon highlight
  for (const room of currentVisualRooms()) {
    if (hoveredRoom === room.name) {
      ctx.save()
      ctx.fillStyle = 'rgba(34,211,238,0.12)'
      ctx.beginPath()
      ctx.roundRect(room.x, room.y, room.width, room.height, 6)
      ctx.fill()
      ctx.strokeStyle = '#22d3ee'
      ctx.lineWidth = 3
      ctx.shadowColor = '#22d3ee'
      ctx.shadowBlur = 15
      ctx.stroke()
      ctx.restore()
    }
  }

  // ---- Draw online role (sprite version) ----
  const allAgents = [...store.onlineAgents]
  if (store.myProfile) {
    const myIdx = allAgents.findIndex(a => a.id === store.myProfile!.id)
    if (myIdx < 0) allAgents.push(store.myProfile as any)
  }

  // Track which agents are present this frame so we can clean up stale entries
  const presentIds = new Set<number>()

  for (const agent of allAgents) {
    const id = agent.id

    // ── floor filter：pos_y Includes floor offset，Decode the floor ──
    const agentFloor = Math.floor(agent.pos_y / FLOOR_Y_OFFSET) + 1
    if (agentFloor !== store.currentFloor) {
      // This role is not on the Current floor，Clean its animationstate and skip rendering
      displayPositions.delete(id)
      prevPositions.delete(id)
      walkFrames.delete(id)
      stillCounters.delete(id)
      continue
    }

    presentIds.add(id)

    const sourceX = agent.pos_x
    const sourceY = agent.pos_y % FLOOR_Y_OFFSET  // Decoding canvasy（Remove floor offset）
    const visualPoint = toVisualPoint(sourceX, sourceY)
    const targetX = visualPoint.x
    const targetY = visualPoint.y
    const color = AVATAR_COLORS[agent.avatar_key] || '#6366f1'

    // --- Interpolate display position toward target ---
    let disp = displayPositions.get(id)
    if (!disp) {
      // First time we see this agent: snap to target
      disp = { x: targetX, y: targetY }
      displayPositions.set(id, disp)
    } else {
      disp.x = lerp(disp.x, targetX, LERP_SPEED)
      disp.y = lerp(disp.y, targetY, LERP_SPEED)
      // Snap when very close to avoid endless tiny drift
      if (Math.abs(disp.x - targetX) < 0.5) disp.x = targetX
      if (Math.abs(disp.y - targetY) < 0.5) disp.y = targetY
    }

    const dx = disp.x - (prevPositions.get(id)?.x ?? disp.x)
    const dy = disp.y - (prevPositions.get(id)?.y ?? disp.y)

    // Determine if the character is visually moving
    const moveDist = Math.sqrt(dx * dx + dy * dy)
    let isMoving: boolean
    if (moveDist > 0.5) {
      stillCounters.set(id, 0)
      isMoving = true
    } else {
      const sc = (stillCounters.get(id) ?? 0) + 1
      stillCounters.set(id, sc)
      isMoving = sc < STOP_THRESHOLD
    }

    // Advance walk frame only while moving
    let wf = walkFrames.get(id) ?? 0
    if (isMoving && tickCounter % 6 === 0) {
      wf = (wf + 1) % 3
      walkFrames.set(id, wf)
    } else if (!isMoving) {
      walkFrames.set(id, 0)
      wf = 0
    }

    const direction = isMoving ? directionFromDelta(dx, dy) : 'down'

    // Store current display position as previous for next frame
    prevPositions.set(id, { x: disp.x, y: disp.y })

    // ---- Draw the sprite ----
    const isMe = agent.id === store.myProfile?.id

    // Draw a neon highlight ring for "my" agent
    if (isMe) {
      ctx.save()
      ctx.strokeStyle = '#22d3ee'
      ctx.lineWidth = 2
      ctx.shadowColor = '#22d3ee'
      ctx.shadowBlur = 10
      ctx.beginPath()
      ctx.ellipse(disp.x, disp.y + 1, 14, 5, 0, 0, Math.PI * 2)
      ctx.stroke()
      ctx.restore()
    }

    drawSprite(ctx, disp.x, disp.y, {
      color,
      direction,
      frame: wf,
      isMoving,
    })

    // Name label above the sprite (chibi is ~40px tall)
    drawNameLabel(ctx, disp.x, disp.y - 44, agent.nickname, agent.career_level)

    // Action bubble (only when not idle)
    const actionLabel = ACTION_LABELS[agent.current_action] || ''
    if (actionLabel && agent.current_action !== 'idle') {
      drawActionBubble(ctx, disp.x, disp.y - 60, actionLabel)
    }
  }

  // Clean up state for agents that left
  for (const id of [...displayPositions.keys()]) {
    if (!presentIds.has(id)) {
      displayPositions.delete(id)
      prevPositions.delete(id)
      walkFrames.delete(id)
      stillCounters.delete(id)
    }
  }

  animFrame = requestAnimationFrame(draw)
}

// ---- Interaction handlers ----

function handleClick(e: MouseEvent) {
  if (!canvasRef.value || !store.myProfile) return
  const rect = canvasRef.value.getBoundingClientRect()
  const scaleX = canvasRef.value.width / rect.width
  const scaleY = canvasRef.value.height / rect.height
  const visualX = Math.round((e.clientX - rect.left) * scaleX)
  const visualY = Math.round((e.clientY - rect.top) * scaleY)

  // Check if other Roles are clicked (use display positions for accurate hit-test)
  const allAgents = store.onlineAgents
  for (const agent of allAgents) {
    if (agent.id === store.myProfile.id) continue
    const disp = displayPositions.get(agent.id)
    const fallback = toVisualPoint(agent.pos_x, agent.pos_y % FLOOR_Y_OFFSET)
    const ax = disp ? disp.x : fallback.x
    const ay = disp ? disp.y : fallback.y
    const ddx = ax - visualX
    const ddy = ay - visualY
    if (ddx * ddx + ddy * ddy < 400) {
      store.selectedAgent = agent
      return
    }
  }

  // Otherwise move
  const sourcePoint = fromVisualPoint(visualX, visualY)
  store.moveAgent(Math.round(sourcePoint.x), Math.round(sourcePoint.y))
}

function handleMouseMove(e: MouseEvent) {
  if (!canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  const scaleX = canvasRef.value.width / rect.width
  const scaleY = canvasRef.value.height / rect.height
  const x = (e.clientX - rect.left) * scaleX
  const y = (e.clientY - rect.top) * scaleY

  hoveredRoom = ''
  for (const room of currentVisualRooms()) {
    if (x >= room.x && x <= room.x + room.width && y >= room.y && y <= room.y + room.height) {
      hoveredRoom = room.name
      break
    }
  }
}

function handleDblClick(e: MouseEvent) {
  if (!canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  const scaleX = canvasRef.value.width / rect.width
  const scaleY = canvasRef.value.height / rect.height
  const x = (e.clientX - rect.left) * scaleX
  const y = (e.clientY - rect.top) * scaleY

  for (const room of currentVisualRooms()) {
    if (x >= room.x && x <= room.x + room.width && y >= room.y && y <= room.y + room.height) {
      emit('enter-room', room.sourceRoom)
      return
    }
  }
}

// ---- Lifecycle ----

onMounted(() => {
  if (canvasRef.value) {
    ctx = canvasRef.value.getContext('2d')
    // Create an off-screen canvas for static element cache
    staticCanvas = document.createElement('canvas')
    staticCanvas.width = CANVAS_WIDTH
    staticCanvas.height = CANVAS_HEIGHT
    staticCtx = staticCanvas.getContext('2d')
    staticDirty = true
    lastFloor = store.currentFloor
    animFrame = requestAnimationFrame(draw)
  }
})

onUnmounted(() => {
  cancelAnimationFrame(animFrame)
  // Clear animation state
  displayPositions.clear()
  prevPositions.clear()
  walkFrames.clear()
  stillCounters.clear()
  // Clean up off-screen canvas
  staticCanvas = null
  staticCtx = null
  staticDirty = true
})
</script>

<template>
  <div class="office-canvas-wrap">
    <div class="floor-tabs">
      <button
        v-for="f in floorKeys"
        :key="f"
        :class="{ active: store.currentFloor === f }"
        @click="store.switchFloor(f)"
      >
        {{ FLOOR_LABELS[f] || f + 'F' }}
      </button>
    </div>
    <canvas
      ref="canvasRef"
      :width="CANVAS_WIDTH"
      :height="CANVAS_HEIGHT"
      class="office-canvas"
      @click="handleClick"
      @dblclick="handleDblClick"
      @mousemove="handleMouseMove"
    />
  </div>
</template>

<style scoped>
.office-canvas-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0a0e1a 0%, #111827 100%);
  border-radius: 12px;
  overflow: hidden;
  padding: 4px;
}
.floor-tabs {
  display: flex;
  gap: 6px;
  padding: 8px 12px;
  width: 100%;
  max-width: 600px;
  justify-content: center;
}
.floor-tabs button {
  border: 1px solid rgba(34,211,238,0.25);
  background: rgba(15,23,42,0.8);
  backdrop-filter: blur(4px);
  padding: 7px 20px;
  border-radius: 20px;
  cursor: pointer;
  font-size: 14px;
  font-family: "Orbitron", "Microsoft YaHei", sans-serif;
  color: rgba(34,211,238,0.7);
  font-weight: 500;
  transition: all 0.25s ease;
}
.floor-tabs button:hover {
  background: rgba(34,211,238,0.1);
  color: #22d3ee;
  transform: translateY(-1px);
  box-shadow: 0 0 12px rgba(34,211,238,0.15);
  border-color: rgba(34,211,238,0.5);
}
.floor-tabs button.active {
  background: linear-gradient(135deg, rgba(34,211,238,0.2), rgba(167,139,250,0.15));
  color: #22d3ee;
  border-color: #22d3ee;
  font-weight: 600;
  box-shadow: 0 0 16px rgba(34,211,238,0.25), inset 0 0 8px rgba(34,211,238,0.08);
}
.office-canvas {
  width: 100%;
  max-width: 600px;
  height: auto;
  cursor: pointer;
  border-radius: 10px;
  box-shadow: 0 0 20px rgba(34,211,238,0.08), 0 4px 16px rgba(0,0,0,0.4);
  border: 1px solid rgba(34,211,238,0.15);
}
</style>
