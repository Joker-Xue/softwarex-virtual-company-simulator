/**
 * WebSocket encapsulation - supports exponential backoff reconnection, reconnection state indication, maximum number of retries
 */

type MessageHandler = (data: any) => void

const RECONNECT_BASE_DELAY = 3000    // Initial reconnection delay 3s
const RECONNECT_MAX_DELAY = 30000    // Maximum reconnection delay 30s
const MAX_RECONNECT_ATTEMPTS = 10    // Maximum number of reconnections

export class AgentWebSocket {
  private ws: WebSocket | null = null
  private url: string
  private handlers: Map<string, MessageHandler[]> = new Map()
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private _connected = false
  private _reconnecting = false
  private _reconnectAttempts = 0

  constructor(baseUrl?: string) {
    const wsBase = baseUrl || (import.meta.env.VITE_API_BASE || window.location.origin).replace(/^http/, 'ws')
    this.url = wsBase
  }

  get connected() {
    return this._connected
  }

  /** Is reconnecting in progress?，Can be used in UI to display reconnection indicator */
  get reconnecting() {
    return this._reconnecting
  }

  /** CurrentThe number of reconnect attempts */
  get reconnectAttempts() {
    return this._reconnectAttempts
  }

  connect(token: string) {
    if (this.ws) this.close()

    const fullUrl = `${this.url}/ws/world?token=${token}`
    this.ws = new WebSocket(fullUrl)

    this.ws.onopen = () => {
      // The backend reads the token from the first msgsinformation for authentication.（No URL query param）
      this.ws!.send(JSON.stringify({ token }))
      this._connected = true
      this._reconnecting = false
      this._reconnectAttempts = 0
      this.emit('connected', {})
      // heartbeat
      this.pingTimer = setInterval(() => {
        this.send({ type: 'ping' })
      }, 30000)
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        const type = data.type || 'unknown'
        this.emit(type, data)
        this.emit('*', data) // wildcard
      } catch {
        // ignore
      }
    }

    this.ws.onclose = (event) => {
      this._connected = false
      this.clearTimers()
      this.emit('disconnected', { code: event.code, reason: event.reason })
      // Automatically reconnect（Inactive shutdown）
      if (event.code !== 4001 && event.code !== 4002 && event.code !== 1000) {
        this._scheduleReconnect(token)
      }
    }

    this.ws.onerror = () => {
      this.emit('error', {})
    }
  }

  /**
   * Exponential backoff reconnection：3s → 6s → 12s → 24s → 30s(max)
   * Stop after MAX_RECONNECT_ATTEMPTS times，Emit max_reconnect event.
   */
  private _scheduleReconnect(token: string) {
    if (this._reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this._reconnecting = false
      this.emit('max_reconnect', { attempts: this._reconnectAttempts })
      return
    }

    this._reconnecting = true
    const delay = Math.min(
      RECONNECT_BASE_DELAY * Math.pow(2, this._reconnectAttempts),
      RECONNECT_MAX_DELAY,
    )
    this._reconnectAttempts++
    this.emit('reconnecting', { attempt: this._reconnectAttempts, delay })

    this.reconnectTimer = setTimeout(() => this.connect(token), delay)
  }

  on(type: string, handler: MessageHandler) {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, [])
    }
    this.handlers.get(type)!.push(handler)
  }

  off(type: string, handler?: MessageHandler) {
    if (!handler) {
      this.handlers.delete(type)
    } else {
      const list = this.handlers.get(type)
      if (list) {
        this.handlers.set(type, list.filter(h => h !== handler))
      }
    }
  }

  private emit(type: string, data: any) {
    const list = this.handlers.get(type)
    if (list) {
      list.forEach(h => h(data))
    }
  }

  send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  move(x: number, y: number) {
    this.send({ type: 'move', x, y })
  }

  setAction(action: string) {
    this.send({ type: 'action', action })
  }

  chat(to: number, content: string) {
    this.send({ type: 'chat', to, content })
  }

  close() {
    this.clearTimers()
    this._reconnecting = false
    this._reconnectAttempts = 0
    if (this.ws) {
      this.ws.close(1000)
      this.ws = null
    }
    this._connected = false
  }

  private clearTimers() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer)
      this.pingTimer = null
    }
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }
}

// Singleton
let instance: AgentWebSocket | null = null

export function getAgentWS(): AgentWebSocket {
  if (!instance) {
    instance = new AgentWebSocket()
  }
  return instance
}
