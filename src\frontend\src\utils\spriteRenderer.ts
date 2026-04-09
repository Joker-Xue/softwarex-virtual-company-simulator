/**
 * Enhanced chibi-style sprite renderer for virtual company agents.
 * Draws cute, detailed pixel characters on Canvas without external images.
 */

export interface SpriteOptions {
  color: string       // primary color for the character's outfit
  direction: 'down' | 'up' | 'left' | 'right'
  frame: number       // 0, 1, or 2 for walk cycle
  isMoving: boolean
}

// ---- color helpers ----

function darken(hex: string, amount: number): string {
  const c = parseInt(hex.replace('#', ''), 16)
  const r = Math.max(0, Math.floor(((c >> 16) & 0xff) * (1 - amount)))
  const g = Math.max(0, Math.floor(((c >> 8) & 0xff) * (1 - amount)))
  const b = Math.max(0, Math.floor((c & 0xff) * (1 - amount)))
  return `rgb(${r},${g},${b})`
}

function lighten(hex: string, amount: number): string {
  const c = parseInt(hex.replace('#', ''), 16)
  const r = Math.min(255, Math.floor(((c >> 16) & 0xff) + (255 - ((c >> 16) & 0xff)) * amount))
  const g = Math.min(255, Math.floor(((c >> 8) & 0xff) + (255 - ((c >> 8) & 0xff)) * amount))
  const b = Math.min(255, Math.floor((c & 0xff) + (255 - (c & 0xff)) * amount))
  return `rgb(${r},${g},${b})`
}

/** Simple seeded hash from color string to pick hair style */
function colorHash(hex: string): number {
  let h = 0
  for (let i = 0; i < hex.length; i++) {
    h = ((h << 5) - h + hex.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

// ---- palette ----

const SKIN = '#fddcb5'
const SKIN_SHADOW = '#ecc298'
const SKIN_HIGHLIGHT = '#feecd2'
const HAIR_COLORS = ['#3b2314', '#5a3825', '#8b6914', '#c24a1a', '#1a1a2e']
const EYE = '#1e1e2e'
const WHITE = '#fff'
const SHOE = '#3f3f46'
const SHOE_HIGHLIGHT = '#52525b'

// ---- main sprite ----

/**
 * Draws a chibi-style character. (x, y) = bottom-center.
 * Bounding box ~28w × 40h.
 */
export function drawSprite(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  options: SpriteOptions
): void {
  const { color, direction, frame, isMoving } = options
  const bx = Math.round(x)
  const by = Math.round(y)

  ctx.save()

  // Walk offsets
  let lLeg = 0, rLeg = 0, lArm = 0, rArm = 0, bounce = 0
  if (isMoving) {
    if (frame === 1) { lLeg = -3; rLeg = 3; lArm = 3; rArm = -3; bounce = -1.5 }
    else if (frame === 2) { lLeg = 3; rLeg = -3; lArm = -3; rArm = 3; bounce = -1.5 }
  }

  // Idle breathing animation (subtle)
  const breathe = !isMoving ? Math.sin(Date.now() / 600) * 0.5 : 0

  const bb = bounce + breathe

  // ── Shadow — glowing circle (department-colored) ──
  ctx.save()
  ctx.shadowColor = color
  ctx.shadowBlur = 10
  ctx.fillStyle = `${color}33`
  ctx.beginPath()
  ctx.ellipse(bx, by + 1, 11, 4, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()

  // ── Determine hair color from outfit color hash ──
  const hIdx = colorHash(color) % HAIR_COLORS.length
  const hairColor = HAIR_COLORS[hIdx]
  const hairHighlight = lighten(hairColor, 0.3)

  // ── Legs ──
  const legW = 5
  const legH = 9
  const legTop = by - legH

  // Left leg
  ctx.fillStyle = darken(color, 0.3)
  ctx.beginPath()
  ctx.roundRect(bx - 6, legTop + lLeg + bb, legW, legH, 2)
  ctx.fill()
  // Shoe
  ctx.fillStyle = SHOE
  ctx.beginPath()
  ctx.roundRect(bx - 7, by - 3 + lLeg + bb, legW + 2, 4, [0, 0, 2, 2])
  ctx.fill()
  ctx.fillStyle = SHOE_HIGHLIGHT
  ctx.fillRect(bx - 6, by - 3 + lLeg + bb, legW, 1)

  // Right leg
  ctx.fillStyle = darken(color, 0.3)
  ctx.beginPath()
  ctx.roundRect(bx + 1, legTop + rLeg + bb, legW, legH, 2)
  ctx.fill()
  ctx.fillStyle = SHOE
  ctx.beginPath()
  ctx.roundRect(bx, by - 3 + rLeg + bb, legW + 2, 4, [0, 0, 2, 2])
  ctx.fill()
  ctx.fillStyle = SHOE_HIGHLIGHT
  ctx.fillRect(bx + 1, by - 3 + rLeg + bb, legW, 1)

  // ── Body (torso) ──
  const bodyW = 16
  const bodyH = 13
  const bodyTop = legTop - bodyH + bb

  // Main body
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.roundRect(bx - bodyW / 2, bodyTop, bodyW, bodyH, 3)
  ctx.fill()

  // Collar / lighter stripe
  ctx.fillStyle = lighten(color, 0.3)
  ctx.beginPath()
  ctx.roundRect(bx - bodyW / 2, bodyTop, bodyW, 3, [3, 3, 0, 0])
  ctx.fill()

  // Shirt detail — center line for button-up look
  ctx.strokeStyle = darken(color, 0.15)
  ctx.lineWidth = 0.6
  ctx.beginPath()
  ctx.moveTo(bx, bodyTop + 3)
  ctx.lineTo(bx, bodyTop + bodyH)
  ctx.stroke()

  // ── Arms ──
  const armW = 4
  const armH = 10

  // Left arm
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.roundRect(bx - bodyW / 2 - armW, bodyTop + 2 + lArm, armW, armH, 2)
  ctx.fill()
  // Hand
  ctx.fillStyle = SKIN
  ctx.beginPath()
  ctx.arc(bx - bodyW / 2 - armW / 2, bodyTop + 2 + armH + lArm, 2.5, 0, Math.PI * 2)
  ctx.fill()

  // Right arm
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.roundRect(bx + bodyW / 2, bodyTop + 2 + rArm, armW, armH, 2)
  ctx.fill()
  ctx.fillStyle = SKIN
  ctx.beginPath()
  ctx.arc(bx + bodyW / 2 + armW / 2, bodyTop + 2 + armH + rArm, 2.5, 0, Math.PI * 2)
  ctx.fill()

  // ── Head ──
  const headR = 9
  const headCY = bodyTop - headR + 2 + bb

  // Hair back (larger shape behind head)
  ctx.fillStyle = hairColor
  ctx.beginPath()
  ctx.ellipse(bx, headCY - 1, headR + 2, headR + 1, 0, Math.PI, Math.PI * 2)
  ctx.fill()

  // Head circle
  ctx.fillStyle = SKIN
  ctx.beginPath()
  ctx.arc(bx, headCY, headR, 0, Math.PI * 2)
  ctx.fill()

  // Face shadow (lower half)
  ctx.fillStyle = SKIN_SHADOW
  ctx.beginPath()
  ctx.arc(bx, headCY + 1, headR, 0.1 * Math.PI, 0.9 * Math.PI)
  ctx.fill()

  // Face highlight (upper cheek)
  ctx.fillStyle = SKIN_HIGHLIGHT
  ctx.beginPath()
  ctx.arc(bx - 2, headCY - 2, 3, 0, Math.PI * 2)
  ctx.fill()

  // ── Hair (front) — varies by direction ──
  ctx.fillStyle = hairColor
  const hairStyle = hIdx % 3

  if (direction === 'up') {
    // Show back of hair
    ctx.beginPath()
    ctx.ellipse(bx, headCY, headR + 1, headR + 1, 0, 0, Math.PI * 2)
    ctx.fill()
    // Hair highlight streak
    ctx.fillStyle = hairHighlight
    ctx.beginPath()
    ctx.ellipse(bx + 2, headCY - 4, 3, 5, 0.2, 0, Math.PI * 2)
    ctx.fill()
  } else {
    // Front hair bangs
    ctx.fillStyle = hairColor
    if (hairStyle === 0) {
      // Straight bangs
      ctx.beginPath()
      ctx.ellipse(bx, headCY - headR + 3, headR + 1, 5, 0, Math.PI, Math.PI * 2)
      ctx.fill()
      ctx.fillRect(bx - headR, headCY - headR + 1, headR * 2, 3)
    } else if (hairStyle === 1) {
      // Side-swept
      ctx.beginPath()
      ctx.ellipse(bx - 2, headCY - headR + 3, headR + 2, 6, -0.15, Math.PI, Math.PI * 2)
      ctx.fill()
    } else {
      // Spiky / messy
      for (let i = -2; i <= 2; i++) {
        ctx.beginPath()
        ctx.ellipse(bx + i * 4, headCY - headR + 2, 3, 6 + Math.abs(i), 0, Math.PI, Math.PI * 2)
        ctx.fill()
      }
    }
    // Hair highlight
    ctx.fillStyle = hairHighlight
    ctx.beginPath()
    ctx.ellipse(bx - 3, headCY - headR + 3, 2, 3, -0.3, 0, Math.PI * 2)
    ctx.fill()

    // ── Face features (only when facing front/side) ──
    if (direction === 'down' || direction === 'left' || direction === 'right') {
      const faceOffX = direction === 'left' ? -2 : direction === 'right' ? 2 : 0

      // Eyes
      const eyeSpacing = direction === 'down' ? 4 : 3
      const eyeY = headCY + 1

      // Eye whites
      ctx.fillStyle = WHITE
      ctx.beginPath()
      ctx.ellipse(bx - eyeSpacing + faceOffX, eyeY, 2.5, 2, 0, 0, Math.PI * 2)
      ctx.fill()
      ctx.beginPath()
      ctx.ellipse(bx + eyeSpacing + faceOffX, eyeY, 2.5, 2, 0, 0, Math.PI * 2)
      ctx.fill()

      // Pupils (shift slightly based on direction)
      const pupilOff = direction === 'left' ? -0.8 : direction === 'right' ? 0.8 : 0
      ctx.fillStyle = EYE
      ctx.beginPath()
      ctx.arc(bx - eyeSpacing + faceOffX + pupilOff, eyeY, 1.3, 0, Math.PI * 2)
      ctx.fill()
      ctx.beginPath()
      ctx.arc(bx + eyeSpacing + faceOffX + pupilOff, eyeY, 1.3, 0, Math.PI * 2)
      ctx.fill()

      // Eye shine
      ctx.fillStyle = WHITE
      ctx.beginPath()
      ctx.arc(bx - eyeSpacing + faceOffX + pupilOff + 0.5, eyeY - 0.5, 0.5, 0, Math.PI * 2)
      ctx.fill()
      ctx.beginPath()
      ctx.arc(bx + eyeSpacing + faceOffX + pupilOff + 0.5, eyeY - 0.5, 0.5, 0, Math.PI * 2)
      ctx.fill()

      // Blush (cute pink cheeks)
      ctx.fillStyle = 'rgba(255,150,150,0.25)'
      ctx.beginPath()
      ctx.ellipse(bx - 6 + faceOffX, eyeY + 3, 2.5, 1.5, 0, 0, Math.PI * 2)
      ctx.fill()
      ctx.beginPath()
      ctx.ellipse(bx + 6 + faceOffX, eyeY + 3, 2.5, 1.5, 0, 0, Math.PI * 2)
      ctx.fill()

      // Mouth
      if (direction === 'down') {
        // Small smile
        ctx.strokeStyle = '#c47a5a'
        ctx.lineWidth = 0.8
        ctx.beginPath()
        ctx.arc(bx + faceOffX, eyeY + 4.5, 2, 0.15 * Math.PI, 0.85 * Math.PI)
        ctx.stroke()
      } else {
        // Side mouth — small dot
        ctx.fillStyle = '#c47a5a'
        ctx.beginPath()
        ctx.arc(bx + faceOffX + (direction === 'left' ? -1 : 1), eyeY + 4, 0.8, 0, Math.PI * 2)
        ctx.fill()
      }
    }
  }

  // ── Side-view body adjustments ──
  if (direction === 'left' || direction === 'right') {
    // Add a small ear on the visible side
    const earX = direction === 'left' ? bx - headR + 1 : bx + headR - 1
    ctx.fillStyle = SKIN
    ctx.beginPath()
    ctx.arc(earX, headCY + 1, 2, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = SKIN_SHADOW
    ctx.beginPath()
    ctx.arc(earX, headCY + 1, 1, 0, Math.PI * 2)
    ctx.fill()
  }

  ctx.restore()
}

// ---- Name label ----

export function drawNameLabel(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  name: string,
  level?: number
): void {
  ctx.save()
  const fontSize = 10
  ctx.font = `bold ${fontSize}px "Microsoft YaHei", sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'bottom'

  const levelStr = level != null ? `Lv.${level} ` : ''
  const fullText = levelStr + name
  const tw = ctx.measureText(fullText).width
  const padX = 5
  const padY = 3
  const bgW = tw + padX * 2
  const bgH = fontSize + padY * 2
  const bgLeft = x - bgW / 2
  const bgTop = y - bgH

  // Background pill — dark with neon border
  ctx.fillStyle = '#111827'
  ctx.beginPath()
  ctx.roundRect(bgLeft, bgTop, bgW, bgH, bgH / 2)
  ctx.fill()
  ctx.strokeStyle = 'rgba(34,211,238,0.5)'
  ctx.lineWidth = 1
  ctx.stroke()

  // Level text (amber glow)
  if (levelStr) {
    ctx.save()
    ctx.shadowColor = '#fbbf24'
    ctx.shadowBlur = 4
    ctx.fillStyle = '#fbbf24'
    ctx.textAlign = 'left'
    ctx.fillText(levelStr, bgLeft + padX, y - padY)
    ctx.restore()
    // Name text (white)
    ctx.fillStyle = '#e2e8f0'
    ctx.textAlign = 'left'
    ctx.fillText(name, bgLeft + padX + ctx.measureText(levelStr).width, y - padY)
  } else {
    ctx.fillStyle = '#e2e8f0'
    ctx.textAlign = 'center'
    ctx.fillText(fullText, x, y - padY)
  }

  ctx.restore()
}

// ---- Action bubble ----

export function drawActionBubble(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  text: string,
  progress?: number
): void {
  ctx.save()
  const fontSize = 10
  ctx.font = `${fontSize}px "Microsoft YaHei", sans-serif`
  const tw = ctx.measureText(text).width
  const paddingX = 6
  const paddingY = 4
  const hasProgress = progress != null && progress >= 0
  const progressBarHeight = 3
  const progressBarGap = 3

  const bgWidth = tw + paddingX * 2
  const bgHeight = fontSize + paddingY * 2 + (hasProgress ? progressBarHeight + progressBarGap : 0)
  const bubbleLeft = x - bgWidth / 2
  const bubbleTop = y - bgHeight

  // Bubble background — dark with neon cyan border
  ctx.fillStyle = 'rgba(10,14,26,0.92)'
  ctx.beginPath()
  ctx.roundRect(bubbleLeft, bubbleTop, bgWidth, bgHeight, 6)
  ctx.fill()
  ctx.strokeStyle = 'rgba(34,211,238,0.6)'
  ctx.lineWidth = 1
  ctx.stroke()

  // Pointer triangle
  ctx.fillStyle = 'rgba(10,14,26,0.92)'
  ctx.beginPath()
  ctx.moveTo(x - 4, y)
  ctx.lineTo(x, y + 4)
  ctx.lineTo(x + 4, y)
  ctx.closePath()
  ctx.fill()
  // Triangle border
  ctx.strokeStyle = 'rgba(34,211,238,0.6)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(x - 4, y)
  ctx.lineTo(x, y + 4)
  ctx.lineTo(x + 4, y)
  ctx.stroke()

  // Text — white
  ctx.fillStyle = '#e2e8f0'
  ctx.font = `${fontSize}px "Microsoft YaHei", sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  ctx.fillText(text, x, bubbleTop + paddingY)

  // Progress bar — cyan gradient
  if (hasProgress) {
    const barWidth = bgWidth - paddingX * 2
    const barLeft = bubbleLeft + paddingX
    const barTop = bubbleTop + fontSize + paddingY + progressBarGap

    ctx.fillStyle = 'rgba(34,211,238,0.15)'
    ctx.beginPath()
    ctx.roundRect(barLeft, barTop, barWidth, progressBarHeight, 2)
    ctx.fill()

    const fillWidth = barWidth * Math.min(1, Math.max(0, progress!))
    if (fillWidth > 0) {
      const barGrad = ctx.createLinearGradient(barLeft, barTop, barLeft + fillWidth, barTop)
      barGrad.addColorStop(0, '#22d3ee')
      barGrad.addColorStop(1, '#34d399')
      ctx.fillStyle = barGrad
      ctx.beginPath()
      ctx.roundRect(barLeft, barTop, fillWidth, progressBarHeight, 2)
      ctx.fill()
    }
  }

  ctx.restore()
}
