<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAgentWorldStore } from '@/stores/agentWorld'
import { CANVAS_WIDTH, CANVAS_HEIGHT, AVATAR_COLORS, ACTION_LABELS, FLOOR_LABELS, getRoomsByFloor, ROOM_FURNITURE, ROOM_ICONS, FLOOR_Y_OFFSET, NAMED_SPOTS, SPOT_COLORS } from '@/constants/companyMap'
import type { RoomConfig, FurnitureItem, NamedSpot } from '@/constants/companyMap'
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
  for (const [name, spot] of Object.entries(NAMED_SPOTS)) {
    if (spot.floor !== floor) continue
    const color = SPOT_COLORS[spot.spot_type]
    const x = spot.x
    const y = spot.y

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

function drawStatic() {
  if (!staticCtx || !staticCanvas) return
  const c = staticCtx
  const w = staticCanvas.width
  const h = staticCanvas.height
  c.clearRect(0, 0, w, h)

  // ── Background: dark cyberpunk floor ──
  const floorGrad = c.createLinearGradient(0, 0, w, h)
  floorGrad.addColorStop(0, '#0f1729')
  floorGrad.addColorStop(1, '#0a0e1a')
  c.fillStyle = floorGrad
  c.fillRect(0, 0, w, h)

  // ── Neon grid pattern ──
  const tileSize = 30
  c.strokeStyle = 'rgba(34,211,238,0.06)'
  c.lineWidth = 0.5
  for (let gx = 0; gx <= w; gx += tileSize) {
    c.beginPath(); c.moveTo(gx, 0); c.lineTo(gx, h); c.stroke()
  }
  for (let gy = 0; gy <= h; gy += tileSize) {
    c.beginPath(); c.moveTo(0, gy); c.lineTo(w, gy); c.stroke()
  }
  // Brighter grid cross-points
  for (let gy = 0; gy <= h; gy += tileSize) {
    for (let gx = 0; gx <= w; gx += tileSize) {
      c.fillStyle = 'rgba(34,211,238,0.08)'
      c.fillRect(gx - 1, gy - 1, 2, 2)
    }
  }

  // ── Floor label at top ──
  const floorLabel = FLOOR_LABELS[store.currentFloor] || `${store.currentFloor}F`
  c.save()
  c.fillStyle = 'rgba(34,211,238,0.08)'
  c.beginPath()
  c.roundRect(w / 2 - 60, 8, 120, 28, 14)
  c.fill()
  c.strokeStyle = 'rgba(34,211,238,0.3)'
  c.lineWidth = 1
  c.stroke()
  c.shadowColor = '#22d3ee'
  c.shadowBlur = 6
  c.fillStyle = '#22d3ee'
  c.font = 'bold 13px "Orbitron", "Microsoft YaHei", sans-serif'
  c.textAlign = 'center'
  c.textBaseline = 'middle'
  c.fillText(floorLabel, w / 2, 22)
  c.restore()

  // ── Draw rooms ──
  for (const room of currentRooms.value) {
    const rx = room.x
    const ry = room.y
    const rw = room.width
    const rh = room.height
    const radius = 4

    // Extract neon color from room.color (department-based)
    const neonColor = room.color
    // Parse the room color to create dark and glow variants
    const rawHex = neonColor.replace('#', '')
    const rc = parseInt(rawHex, 16)
    const rr = (rc >> 16) & 0xff, rg = (rc >> 8) & 0xff, rb = rc & 0xff

    // Room fill: very dark tinted version of department color
    c.save()
    c.fillStyle = `rgba(${rr},${rg},${rb},0.08)`
    c.beginPath()
    c.roundRect(rx, ry, rw, rh, radius)
    c.fill()

    // Dark base fill
    c.fillStyle = 'rgba(15,23,42,0.85)'
    c.beginPath()
    c.roundRect(rx, ry, rw, rh, radius)
    c.fill()

    // Department-colored tint overlay
    c.fillStyle = `rgba(${rr},${rg},${rb},0.06)`
    c.beginPath()
    c.roundRect(rx, ry, rw, rh, radius)
    c.fill()

    // Neon border with glow
    c.shadowColor = neonColor
    c.shadowBlur = 8
    c.strokeStyle = neonColor
    c.lineWidth = 1.5
    c.beginPath()
    c.roundRect(rx, ry, rw, rh, radius)
    c.stroke()
    c.shadowBlur = 0
    c.restore()

    // ── Door indicator (bottom center of room) — neon accent marker ──
    const doorW = 18
    const doorH = 4
    const doorX = rx + rw / 2 - doorW / 2
    const doorY = ry + rh - 1
    c.save()
    c.shadowColor = '#22d3ee'
    c.shadowBlur = 6
    c.fillStyle = 'rgba(34,211,238,0.6)'
    c.beginPath()
    c.roundRect(doorX, doorY - doorH, doorW, doorH + 1, [0, 0, 2, 2])
    c.fill()
    c.restore()

    // ── Room header bar ──
    c.save()
    c.beginPath()
    c.roundRect(rx, ry, rw, 28, [radius, radius, 0, 0])
    c.clip()
    c.fillStyle = `rgba(${rr},${rg},${rb},0.15)`
    c.fillRect(rx, ry, rw, 28)
    // Neon accent line at bottom of header
    c.strokeStyle = neonColor
    c.lineWidth = 1
    c.globalAlpha = 0.5
    c.beginPath()
    c.moveTo(rx, ry + 28)
    c.lineTo(rx + rw, ry + 28)
    c.stroke()
    c.globalAlpha = 1.0
    c.restore()

    // Room icon + name
    const icon = ROOM_ICONS[room.type] || '🏢'
    c.font = '13px sans-serif'
    c.textAlign = 'center'
    c.textBaseline = 'middle'
    c.fillText(icon, rx + 16, ry + 15)

    c.fillStyle = '#e2e8f0'
    c.font = 'bold 12px "Orbitron", "Microsoft YaHei", sans-serif'
    c.textAlign = 'center'
    c.fillText(room.name, rx + rw / 2 + 8, ry + 15)

    // ── Furniture ──
    const furnitureList = ROOM_FURNITURE[room.type] || []
    for (const item of furnitureList) {
      drawFurniture(c, room, item)
    }
  }

  // ── Corridor decorations (neon marker lights in corners) ──
  const plantPositions = [
    { x: 10, y: 50 }, { x: w - 10, y: 50 },
    { x: 10, y: h - 10 }, { x: w - 10, y: h - 10 },
  ]
  for (const p of plantPositions) {
    c.save()
    c.shadowColor = '#22d3ee'
    c.shadowBlur = 6
    c.fillStyle = 'rgba(34,211,238,0.4)'
    c.beginPath()
    c.arc(p.x, p.y, 3, 0, Math.PI * 2)
    c.fill()
    c.restore()
  }

  // ── Named spot indicators ──
  drawNamedSpots(c, store.currentFloor)

  // ── Spot legend (bottom-right corner) ──
  const legendItems: Array<{ label: string; color: string }> = [
    { label: 'executive anchor', color: SPOT_COLORS.anchor },
    { label: 'desk',     color: SPOT_COLORS.work },
    { label: "Visitor's seat",   color: SPOT_COLORS.visitor },
    { label: 'Rest area',   color: SPOT_COLORS.rest },
    { label: 'meeting chair',   color: SPOT_COLORS.meeting },
  ]
  const legendX = w - 72
  const legendStartY = h - 6 - legendItems.length * 14
  c.save()
  c.fillStyle = 'rgba(10,14,26,0.7)'
  c.beginPath()
  c.roundRect(legendX - 6, legendStartY - 6, 78, legendItems.length * 14 + 10, 4)
  c.fill()
  for (let i = 0; i < legendItems.length; i++) {
    const ly = legendStartY + i * 14
    c.shadowColor = legendItems[i].color
    c.shadowBlur = 4
    c.fillStyle = legendItems[i].color
    c.beginPath()
    c.arc(legendX + 4, ly + 4, 3, 0, Math.PI * 2)
    c.fill()
    c.shadowBlur = 0
    c.fillStyle = 'rgba(226,232,240,0.8)'
    c.font = '9px "Microsoft YaHei", sans-serif'
    c.textAlign = 'left'
    c.textBaseline = 'top'
    c.fillText(legendItems[i].label, legendX + 10, ly)
  }
  c.restore()

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
  for (const room of currentRooms.value) {
    if (hoveredRoom === room.name) {
      const rawHex = room.color.replace('#', '')
      const hc = parseInt(rawHex, 16)
      const hr = (hc >> 16) & 0xff, hg = (hc >> 8) & 0xff, hb = hc & 0xff
      ctx.save()
      ctx.fillStyle = `rgba(${hr},${hg},${hb},0.12)`
      ctx.beginPath()
      ctx.roundRect(room.x, room.y, room.width, room.height, 4)
      ctx.fill()
      ctx.shadowColor = room.color
      ctx.shadowBlur = 12
      ctx.strokeStyle = room.color
      ctx.lineWidth = 2
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

    const targetX = agent.pos_x
    const targetY = agent.pos_y % FLOOR_Y_OFFSET  // Decoding canvasy（Remove floor offset）
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
  const x = Math.round((e.clientX - rect.left) * scaleX)
  const y = Math.round((e.clientY - rect.top) * scaleY)

  // Check if other Roles are clicked (use display positions for accurate hit-test)
  const allAgents = store.onlineAgents
  for (const agent of allAgents) {
    if (agent.id === store.myProfile.id) continue
    const disp = displayPositions.get(agent.id)
    const ax = disp ? disp.x : agent.pos_x
    const ay = disp ? disp.y : agent.pos_y
    const ddx = ax - x
    const ddy = ay - y
    if (ddx * ddx + ddy * ddy < 400) {
      store.selectedAgent = agent
      return
    }
  }

  // Otherwise move
  store.moveAgent(x, y)
}

function handleMouseMove(e: MouseEvent) {
  if (!canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  const scaleX = canvasRef.value.width / rect.width
  const scaleY = canvasRef.value.height / rect.height
  const x = (e.clientX - rect.left) * scaleX
  const y = (e.clientY - rect.top) * scaleY

  hoveredRoom = ''
  for (const room of currentRooms.value) {
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

  for (const room of currentRooms.value) {
    if (x >= room.x && x <= room.x + room.width && y >= room.y && y <= room.y + room.height) {
      emit('enter-room', room)
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
  font-size: 12px;
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
