/**
 * Virtual world Pinia store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import request from '@/utils/request'
import { getAgentWS } from '@/utils/websocket'
import { CAREER_LEVELS, getRoomsByFloor, FLOOR_Y_OFFSET } from '@/constants/companyMap'
import type { RoomConfig } from '@/constants/companyMap'

export interface ScheduleEntry {
  time: string
  activity: string
  room_type: string
}

export interface AgentProfile {
  id: number
  user_id: number
  nickname: string
  avatar_key: string
  mbti: string
  personality: string[]
  attr_communication: number
  attr_leadership: number
  attr_creativity: number
  attr_technical: number
  attr_teamwork: number
  attr_diligence: number
  career_level: number
  career_title: string
  department: string
  tasks_completed: number
  xp: number
  pos_x: number
  pos_y: number
  current_action: string
  is_online: boolean
  ai_enabled: boolean
  daily_schedule: ScheduleEntry[]
}

export interface AgentTask {
  id: number
  title: string
  description: string
  task_type: string
  difficulty: number
  xp_reward: number
  assigner_id: number | null
  assignee_id: number
  status: string
  deadline: string | null
  completed_at: string | null
  created_at: string
}

export interface Friend {
  id: number
  from_id: number
  to_id: number
  status: string
  friend_nickname: string
  friend_avatar: string
  friend_level: number
  friend_department: string
  friend_mbti: string
  affinity: number
  compatibility_score: number
  compatibility_label: string
  role: string  // "mentor" / "mentee" / ""
}

export interface ChatMessage {
  id: number
  sender_id: number
  receiver_id: number
  content: string
  msg_type: string
  is_read: boolean
  created_at: string
}

export interface AgentMemoryItem {
  id: number
  content: string
  memory_type: string
  importance: number
  related_agent_id: number | null
  created_at: string
}

export interface InteriorObject {
  type: string
  name: string
  x: number
  y: number
  width: number
  height: number
  interactive: boolean
}

export interface CompanyRoom {
  id: number
  name: string
  room_type: string
  department: string
  x: number
  y: number
  width: number
  height: number
  capacity: number
  floor: number
  interior_objects: InteriorObject[]
  description: string | null
}

export interface InteractionSpot {
  id: string
  name: string
  x: number
  y: number
  floor: number
  spot_type: string
  room_id: number
}

export interface ObjectAction {
  object_key: string
  action_key: string
  action_type: string
  task_tags: string[]
  cooldown_sec: number
  duration_sec: number
}

export interface ObjectOccupancy {
  object_key: string
  occupant_agent_id: number | null
  lock_until: string | null
  queue_count: number
}

export interface RoomInteractions {
  room_id: number
  interaction_spots: InteractionSpot[]
  object_actions: ObjectAction[]
  occupancies: ObjectOccupancy[]
  metrics: Record<string, any>
}

export interface MoveInsideResult {
  room_id: number
  spot: InteractionSpot
  pos_x: number
  pos_y: number
}

export interface InteractResult {
  success: boolean
  reason: string
  task_delta: number
  xp_delta: number
  level_up: boolean
  cooldown_left_sec: number
  queue_count: number
  occupancy?: ObjectOccupancy
}

export const useAgentWorldStore = defineStore('agentWorld', () => {
  // State
  const myProfile = ref<AgentProfile | null>(null)
  const onlineAgents = ref<AgentProfile[]>([])
  const tasks = ref<AgentTask[]>([])
  const friends = ref<Friend[]>([])
  const pendingRequests = ref<any[]>([])
  const sentRequests = ref<any[]>([])
  const receivedHistory = ref<any[]>([])
  const chatMessages = ref<ChatMessage[]>([])
  const chatTarget = ref<number | null>(null)
  const selectedAgent = ref<AgentProfile | null>(null)
  const unreadCount = ref(0)
  const unreadPerSender = ref<Record<number, number>>({})
  const wsConnected = ref(false)
  const memories = ref<AgentMemoryItem[]>([])
  const memoriesTotalCount = ref(0)
  const currentFloor = ref(1)
  const roomMap = ref<CompanyRoom[]>([])
  const personalityTrace = ref<any>(null)
  const taskStatus = ref<any>(null)
  // Private-chat AI typing state
  const aiTyping = ref(false)
  // Real-time channel message push (components watch this value to handle new messages)
  const lastChannelMessage = ref<{ group_id: string; message: any } | null>(null)
  // Friend request approval notification
  const friendAcceptedNotif = ref<{ nickname: string } | null>(null)

  // Computed
  const hasProfile = computed(() => !!myProfile.value)
  const careerTitle = computed(() => {
    if (!myProfile.value) return ''
    return CAREER_LEVELS[myProfile.value.career_level]?.title || 'Unknown'
  })
  const nextLevel = computed(() => {
    if (!myProfile.value) return null
    const next = myProfile.value.career_level + 1
    return CAREER_LEVELS[next] || null
  })

  /** CurrentFloor room configuration */
  const currentFloorRooms = computed<RoomConfig[]>(() => {
    return getRoomsByFloor(currentFloor.value)
  })

  /** Judging whether a coordinate point falls on a certain floor - decoding through floor Y offset encoding */
  function isAgentOnFloor(agent: AgentProfile, floor: number): boolean {
    // pos_y Includes floor offset：floor = Math.floor(pos_y / FLOOR_Y_OFFSET) + 1
    const agentFloor = Math.floor(agent.pos_y / FLOOR_Y_OFFSET) + 1
    return agentFloor === floor
  }

  /** Current Floor Online Role（In a certain room on this floor or in a Role whose coordinates are in the corridor area） */
  const currentFloorAgents = computed<AgentProfile[]>(() => {
    return onlineAgents.value.filter(a => isAgentOnFloor(a, currentFloor.value))
  })

  // Actions
  function switchFloor(floor: number) {
    if (floor >= 1 && floor <= 3) {
      currentFloor.value = floor
    }
  }

  async function fetchMap() {
    try {
      const { data } = await request.get('/api/world/map')
      roomMap.value = data
      return data
    } catch {
      roomMap.value = []
      return []
    }
  }

  async function fetchProfile() {
    try {
      const { data } = await request.get('/api/agent/profile')
      myProfile.value = data
      return data
    } catch {
      myProfile.value = null
      return null
    }
  }

  async function createProfile(body: any) {
    const { data } = await request.post('/api/agent/profile', body)
    myProfile.value = data
    return data
  }

  async function fetchOnlineAgents() {
    const { data } = await request.get('/api/world/agents/online')
    onlineAgents.value = data
  }

  async function moveAgent(x: number, y: number) {
    // Encode canvas coordinates as floor offset pos_y，Then pass WebSocketSend
    const encodedY = y + (currentFloor.value - 1) * FLOOR_Y_OFFSET
    const ws = getAgentWS()
    ws.move(x, encodedY)
    if (myProfile.value) {
      myProfile.value.pos_x = x
      myProfile.value.pos_y = encodedY
    }
  }

  async function fetchRoomInteractions(roomId: number): Promise<RoomInteractions> {
    const { data } = await request.get(`/api/world/rooms/${roomId}/interactions`)
    return data
  }

  async function moveInsideRoom(roomId: number, x: number, y: number): Promise<MoveInsideResult> {
    const { data } = await request.post(`/api/world/rooms/${roomId}/move-inside`, { x, y })
    if (myProfile.value) {
      myProfile.value.pos_x = data.pos_x
      myProfile.value.pos_y = data.pos_y
      myProfile.value.current_action = 'moving'
    }
    return data
  }

  async function interactInsideRoom(roomId: number, objectKey: string): Promise<InteractResult> {
    const { data } = await request.post(`/api/world/rooms/${roomId}/interact`, { object_key: objectKey })
    if (data.success && myProfile.value && typeof data.xp_delta === 'number') {
      myProfile.value.xp += data.xp_delta
    }
    return data
  }

  async function fetchTasks(status?: string) {
    const params = status ? { status } : {}
    const { data } = await request.get('/api/task/my', { params })
    tasks.value = data
  }

  async function generateTasks() {
    const { data } = await request.post('/api/task/generate')
    tasks.value = [...data, ...tasks.value]
    return data
  }

  async function completeTask(taskId: number) {
    const { data } = await request.post(`/api/task/${taskId}/complete`)
    // Update local Taskstate
    const idx = tasks.value.findIndex(t => t.id === taskId)
    if (idx >= 0) tasks.value[idx].status = 'completed'
    // Update profile
    if (myProfile.value && data.career_level !== undefined) {
      myProfile.value.xp = data.total_xp
      myProfile.value.tasks_completed = data.tasks_completed
      myProfile.value.career_level = data.career_level
    }
    return data
  }

  async function fetchFriends() {
    const { data } = await request.get('/api/friend/list')
    friends.value = data
  }

  async function fetchPendingRequests() {
    const { data } = await request.get('/api/friend/pending')
    pendingRequests.value = data
  }

  async function fetchSentRequests() {
    const { data } = await request.get('/api/friend/sent')
    sentRequests.value = data
  }

  async function fetchReceivedHistory() {
    const { data } = await request.get('/api/friend/received')
    receivedHistory.value = data
  }

  async function sendFriendRequest(agentId: number) {
    await request.post(`/api/friend/request/${agentId}`)
  }

  async function acceptFriend(id: number) {
    await request.post(`/api/friend/accept/${id}`)
    await fetchFriends()
    await fetchPendingRequests()
  }

  async function rejectFriend(id: number) {
    await request.post(`/api/friend/reject/${id}`)
    await fetchPendingRequests()
  }

  async function fetchMessages(agentId: number) {
    chatTarget.value = agentId
    const { data } = await request.get(`/api/agent-chat/messages/${agentId}`)
    chatMessages.value = data
    await request.post(`/api/agent-chat/read/${agentId}`)
    // Clear per-sender unread and update total
    const prev = unreadPerSender.value[agentId] || 0
    if (prev > 0) {
      unreadPerSender.value[agentId] = 0
      unreadCount.value = Math.max(0, unreadCount.value - prev)
    }
  }

  async function sendMessage(receiverId: number, content: string) {
    const { data } = await request.post('/api/agent-chat/send', {
      receiver_id: receiverId,
      content,
    })
    chatMessages.value.push(data)
    // Also via WSSend
    const ws = getAgentWS()
    ws.chat(receiverId, content)
    // If the opponent is an AI character，show"Entering"state（The backend will push the reply through WS）
    const targetFriend = friends.value.find(
      f => (f.from_id === myProfile.value?.id ? f.to_id : f.from_id) === receiverId
    )
    if (data.msg_type !== 'ai_generated') {
      // Check if the target is an AIRole（Via online agents list）
      const targetAgent = onlineAgents.value.find(a => a.id === receiverId)
      if (targetAgent?.ai_enabled) {
        aiTyping.value = true
      }
    }
  }

  async function fetchUnread() {
    const { data } = await request.get('/api/agent-chat/unread')
    unreadCount.value = data.unread
  }

  async function fetchUnreadPerSender() {
    const { data } = await request.get('/api/agent-chat/unread-by-sender')
    const result: Record<number, number> = {}
    for (const [k, v] of Object.entries(data as Record<string, number>)) {
      result[Number(k)] = v
    }
    unreadPerSender.value = result
    unreadCount.value = Object.values(result).reduce((a, b) => a + b, 0)
  }

  async function fetchMemories(page = 1, pageSize = 20, memoryType?: string) {
    const params: Record<string, any> = { page, page_size: pageSize }
    if (memoryType) params.memory_type = memoryType
    const { data } = await request.get('/api/agent-chat/memories', { params })
    memories.value = data.memories
    memoriesTotalCount.value = data.total
    return data
  }

  async function fetchPersonalityTrace() {
    try {
      const { data } = await request.get('/api/agent/personality-trace')
      personalityTrace.value = data
    } catch { /* ignore */ }
  }

  async function fetchTaskStatus() {
    try {
      const { data } = await request.get('/api/agent/task-status')
      taskStatus.value = data
    } catch { /* ignore */ }
  }

  function connectWS() {
    const token = localStorage.getItem('token')
    if (!token) return

    const ws = getAgentWS()
    ws.connect(token)

    ws.on('connected', () => { wsConnected.value = true })
    ws.on('disconnected', () => { wsConnected.value = false })

    ws.on('agent_join', (data: any) => {
      const agent = data.agent as AgentProfile
      const idx = onlineAgents.value.findIndex(a => a.id === agent.id)
      if (idx >= 0) {
        onlineAgents.value[idx] = { ...onlineAgents.value[idx], ...agent, is_online: true }
      } else {
        onlineAgents.value.push({ ...agent, is_online: true } as AgentProfile)
      }
    })

    ws.on('agent_leave', (data: any) => {
      onlineAgents.value = onlineAgents.value.filter(a => a.id !== data.agent_id)
    })

    ws.on('agent_move', (data: any) => {
      const agent = onlineAgents.value.find(a => a.id === data.agent_id)
      if (agent) {
        agent.pos_x = data.x
        agent.pos_y = data.y
      }
    })

    ws.on('agent_action', (data: any) => {
      const agent = onlineAgents.value.find(a => a.id === data.agent_id)
      if (agent) {
        agent.current_action = data.action
      }
    })

    ws.on('new_message', (data: any) => {
      // Clear when receiving information"Entering"state
      aiTyping.value = false
      if (data.from === chatTarget.value) {
        chatMessages.value.push({
          id: data.msg_id || Date.now(),
          sender_id: data.from,
          receiver_id: myProfile.value?.id || 0,
          content: data.content,
          msg_type: data.msg_type || 'text',
          is_read: true,
          created_at: new Date().toISOString(),
        })
      } else {
        unreadCount.value++
        unreadPerSender.value[data.from] = (unreadPerSender.value[data.from] || 0) + 1
      }
    })

    ws.on('channel_message', (data: any) => {
      // Channelsreal-time information：Update lastChannelMessage，Whether the component's own Judging is appended
      lastChannelMessage.value = {
        group_id: data.group_id,
        message: data.message,
      }
    })

    ws.on('friend_accepted', (data: any) => {
      // NPC Apply through friend：Automatically refresh Friend List and issued application state
      friendAcceptedNotif.value = { nickname: data.nickname || 'NPC' }
      fetchFriends()
      fetchSentRequests()
    })

    ws.on('promotion', (data: any) => {
      if (myProfile.value && data.agent_id === myProfile.value.id) {
        myProfile.value.career_level = data.new_level
      }
    })

    // Simulate engine broadcast：Update all agent locations and statuses in batches
    ws.on('sim_update', (data: any) => {
      if (Array.isArray(data.agents)) {
        for (const agentData of data.agents) {
          const existing = onlineAgents.value.find(a => a.id === agentData.id)
          if (existing) {
            existing.pos_x = agentData.pos_x
            existing.pos_y = agentData.pos_y
            existing.current_action = agentData.current_action
            existing.career_level = agentData.career_level
          } else {
            onlineAgents.value.push({
              id: agentData.id,
              nickname: agentData.nickname,
              pos_x: agentData.pos_x,
              pos_y: agentData.pos_y,
              current_action: agentData.current_action,
              career_level: agentData.career_level,
              department: agentData.department,
              avatar_key: agentData.avatar_key,
              is_online: true,
            } as AgentProfile)
          }
        }
      }
    })
  }

  function disconnectWS() {
    const ws = getAgentWS()
    ws.close()
    wsConnected.value = false
  }

  function reset() {
    disconnectWS()
    myProfile.value = null
    onlineAgents.value = []
    tasks.value = []
    friends.value = []
    pendingRequests.value = []
    sentRequests.value = []
    receivedHistory.value = []
    chatMessages.value = []
    chatTarget.value = null
    selectedAgent.value = null
    unreadCount.value = 0
    unreadPerSender.value = {}
    memories.value = []
    memoriesTotalCount.value = 0
    roomMap.value = []
    personalityTrace.value = null
    taskStatus.value = null
    aiTyping.value = false
    lastChannelMessage.value = null
    friendAcceptedNotif.value = null
    currentFloor.value = 1
  }

  return {
    myProfile, onlineAgents, tasks, friends, pendingRequests, sentRequests, receivedHistory,
    chatMessages, chatTarget, selectedAgent, unreadCount, unreadPerSender, wsConnected,
    memories, memoriesTotalCount, roomMap,
    personalityTrace, taskStatus,
    aiTyping, lastChannelMessage, friendAcceptedNotif,
    currentFloor, currentFloorRooms, currentFloorAgents,
    hasProfile, careerTitle, nextLevel,
    fetchProfile, createProfile, fetchOnlineAgents, moveAgent,
    fetchRoomInteractions, moveInsideRoom, interactInsideRoom,
    fetchTasks, generateTasks, completeTask,
    fetchFriends, fetchPendingRequests, fetchSentRequests, fetchReceivedHistory,
    sendFriendRequest, acceptFriend, rejectFriend,
    fetchMessages, sendMessage, fetchUnread, fetchUnreadPerSender,
    fetchMemories, fetchMap,
    fetchPersonalityTrace, fetchTaskStatus,
    switchFloor,
    connectWS, disconnectWS, reset,
  }
})
