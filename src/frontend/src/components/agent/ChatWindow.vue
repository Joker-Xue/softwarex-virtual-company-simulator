<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import { useAgentWorldStore } from '@/stores/agentWorld'
import request from '@/utils/request'

const store = useAgentWorldStore()
const input = ref('')
const messagesEl = ref<HTMLDivElement | null>(null)

const chatMode = ref<'private' | 'group'>('private')
const groups = ref<any[]>([])
const activeGroupId = ref<string | null>(null)
const groupMessages = ref<any[]>([])
const groupLoading = ref(false)

onMounted(async () => {
  if (store.chatTarget && store.chatMessages.length === 0) {
    store.fetchMessages(store.chatTarget)
  }
  await fetchGroups()
  store.fetchUnreadPerSender()
})

watch(() => store.chatMessages.length, async () => { await nextTick(); scrollToBottom() })
watch(() => store.aiTyping, async (val) => { if (val) { await nextTick(); scrollToBottom() } })
watch(() => groupMessages.value.length, async () => { await nextTick(); scrollToBottom() })

// 监听频道实时消息（WS推送）
watch(() => store.lastChannelMessage, (val) => {
  if (!val || val.group_id !== activeGroupId.value) return
  if (!groupMessages.value.some(m => m.id === val.message.id)) {
    groupMessages.value.push(val.message)
  }
}, { deep: true })

function scrollToBottom() {
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

async function fetchGroups() {
  try {
    const { data } = await request.get('/api/agent-chat/groups')
    groups.value = Array.isArray(data) ? data : []
  } catch { groups.value = [] }
}

async function fetchGroupMessages(groupId: string) {
  activeGroupId.value = groupId
  groupLoading.value = true
  try {
    const { data } = await request.get(`/api/agent-chat/group/${groupId}/messages`)
    groupMessages.value = Array.isArray(data) ? data : []
  } catch { groupMessages.value = [] }
  finally { groupLoading.value = false }
}

async function send() {
  const content = input.value.trim()
  if (!content) return
  input.value = ''
  if (chatMode.value === 'group' && activeGroupId.value) {
    try {
      const { data } = await request.post(`/api/agent-chat/group/${activeGroupId.value}/send`, { content })
      groupMessages.value.push(data)
    } catch { /* ignore */ }
  } else if (chatMode.value === 'private' && store.chatTarget) {
    try { await store.sendMessage(store.chatTarget, content) } catch { /* ignore */ }
  }
}

function selectFriend(agentId: number) {
  chatMode.value = 'private'
  activeGroupId.value = null
  store.aiTyping = false
  store.fetchMessages(agentId)
}

function selectGroup(groupId: string) {
  chatMode.value = 'group'
  store.chatTarget = null
  fetchGroupMessages(groupId)
}

function goBack() {
  if (chatMode.value === 'group') { activeGroupId.value = null }
  else { store.chatTarget = null; store.aiTyping = false }
}

function currentGroupName() {
  return groups.value.find(g => g.group_id === activeGroupId.value)?.name || '群聊'
}
</script>

<template>
  <div class="chat-window">
    <!-- 列表视图 -->
    <div v-if="!store.chatTarget && !activeGroupId" class="chat-select cyber-scroll">
      <div class="mode-switch">
        <button :class="{ active: chatMode === 'private' }" @click="chatMode = 'private'">私聊</button>
        <button :class="{ active: chatMode === 'group' }" @click="chatMode = 'group'">频道</button>
      </div>
      <template v-if="chatMode === 'private'">
        <div v-for="f in store.friends" :key="f.id" class="chat-friend-item"
          @click="selectFriend(f.from_id === store.myProfile?.id ? f.to_id : f.from_id)">
          <span class="friend-name">{{ f.friend_nickname }}</span>
          <span v-if="f.friend_mbti" class="friend-meta">{{ f.friend_mbti }}</span>
          <span
            v-if="store.unreadPerSender[f.from_id === store.myProfile?.id ? f.to_id : f.from_id]"
            class="unread-dot"
          >{{ store.unreadPerSender[f.from_id === store.myProfile?.id ? f.to_id : f.from_id] }}</span>
        </div>
        <p v-if="store.friends.length === 0" class="hint">暂无好友</p>
      </template>
      <template v-else>
        <div v-for="g in groups" :key="g.group_id" class="chat-friend-item group-item" @click="selectGroup(g.group_id)">
          <span class="group-icon">{{ g.group_type === 'announcement' ? '📢' : g.group_type === 'department' ? '🏢' : '💬' }}</span>
          <span class="friend-name">{{ g.name }}</span>
          <span v-if="g.message_count" class="msg-count">{{ g.message_count }}条</span>
        </div>
        <p v-if="groups.length === 0" class="hint">暂无频道</p>
      </template>
    </div>

    <!-- 聊天视图 -->
    <template v-else>
      <div class="chat-header">
        <span class="back" @click="goBack">&larr; 返回</span>
        <span class="chat-with">{{ activeGroupId ? currentGroupName() : '私聊' }}</span>
      </div>

      <div class="messages cyber-scroll" ref="messagesEl">
        <!-- 私聊 -->
        <template v-if="chatMode === 'private'">
          <div v-for="msg in store.chatMessages" :key="msg.id" class="msg-row"
            :class="{ mine: msg.sender_id === store.myProfile?.id }">
            <div class="msg-bubble">
              <span v-if="msg.msg_type === 'ai_generated'" class="ai-badge">AI</span>{{ msg.content }}
            </div>
            <div class="msg-time">{{ new Date(msg.created_at).toLocaleTimeString() }}</div>
          </div>
          <div v-if="store.aiTyping" class="msg-row typing-row">
            <div class="msg-bubble typing-bubble">
              <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
            </div>
          </div>
        </template>

        <!-- 频道 -->
        <template v-else>
          <div v-if="groupLoading" class="hint" style="padding:20px 0">加载中...</div>
          <template v-else>
            <div v-for="msg in groupMessages" :key="msg.id" class="msg-row"
              :class="{ mine: msg.sender_id === store.myProfile?.id }">
              <div v-if="msg.sender_id !== store.myProfile?.id" class="sender-name">
                {{ msg.sender_nickname || '未知' }}
                <span v-if="msg.msg_type === 'ai_generated'" class="ai-badge">AI</span>
              </div>
              <div class="msg-bubble">{{ msg.content }}</div>
              <div class="msg-time">{{ msg.created_at ? new Date(msg.created_at).toLocaleTimeString() : '' }}</div>
            </div>
          </template>
        </template>

        <div v-if="!groupLoading && (chatMode === 'private' ? store.chatMessages : groupMessages).length === 0"
          class="hint" style="padding:32px 0">暂无消息</div>
      </div>

      <div v-if="activeGroupId === 'announcement'" class="readonly-hint">📢 公告频道由AI自动维护，仅可查看</div>
      <div v-else class="chat-input">
        <el-input v-model="input" placeholder="输入消息..." @keyup.enter="send" size="default" />
        <button class="cyber-btn" @click="send" :disabled="!input.trim()">发送</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.chat-window { display:flex; flex-direction:column; height:100%; min-height:400px; font-family:var(--font-body); }
.chat-select { padding:8px 0; overflow-y:auto; }
.hint { text-align:center; color:var(--text-muted); font-size:13px; }
.mode-switch { display:flex; gap:4px; margin-bottom:10px; background:var(--bg-card); border-radius:var(--radius-md); padding:3px; border:1px solid var(--border-dim); }
.mode-switch button { flex:1; border:none; background:none; padding:6px; font-size:13px; border-radius:var(--radius-sm); cursor:pointer; color:var(--text-muted); font-family:var(--font-body); transition:all var(--duration-base); }
.mode-switch button.active { background:transparent; color:var(--accent-cyan); font-weight:600; border-bottom:2px solid var(--accent-cyan); text-shadow:0 0 8px rgba(34,211,238,0.4); }
.chat-friend-item { padding:10px 12px; border-radius:var(--radius-sm); cursor:pointer; font-size:14px; display:flex; align-items:center; gap:8px; border-bottom:1px solid var(--border-dim); transition:background var(--duration-base); }
.chat-friend-item:hover { background:var(--bg-hover); }
.friend-name { font-weight:600; flex:1; color:var(--text-primary); }
.friend-meta { font-size:11px; color:var(--accent-violet); font-family:var(--font-mono); }
.group-icon { font-size:16px; }
.msg-count { font-size:11px; color:var(--text-muted); font-family:var(--font-mono); }
.unread-dot {
  min-width: 18px; height: 18px; padding: 0 5px;
  border-radius: 9px; background: var(--accent-rose);
  color: #fff; font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-mono);
  box-shadow: 0 0 8px rgba(251,113,133,0.5);
  animation: unread-pulse 2s ease-in-out infinite;
}
@keyframes unread-pulse {
  0%, 100% { box-shadow: 0 0 6px rgba(251,113,133,0.4); }
  50% { box-shadow: 0 0 12px rgba(251,113,133,0.8); }
}
.chat-header { display:flex; align-items:center; gap:12px; padding-bottom:10px; border-bottom:1px solid var(--border-dim); margin-bottom:8px; }
.back { font-size:13px; color:var(--accent-cyan); cursor:pointer; text-shadow:0 0 6px rgba(34,211,238,0.3); }
.chat-with { font-weight:600; font-size:14px; color:var(--text-primary); }
.messages { flex:1; overflow-y:auto; display:flex; flex-direction:column; gap:8px; background:var(--bg-card); border-radius:var(--radius-sm); padding:8px; }
.msg-row { display:flex; flex-direction:column; max-width:80%; }
.msg-row.mine { align-self:flex-end; align-items:flex-end; }
.sender-name { font-size:11px; color:var(--accent-violet); margin-bottom:2px; font-weight:500; display:flex; align-items:center; gap:4px; }
.ai-badge { display:inline-block; font-size:9px; padding:1px 4px; background:rgba(167,139,250,0.15); color:var(--accent-violet); border:1px solid rgba(167,139,250,0.3); border-radius:3px; font-family:var(--font-mono); }
.msg-bubble { padding:8px 12px; border-radius:var(--radius-md); font-size:14px; background:rgba(167,139,250,0.04); color:var(--text-primary); border-left:3px solid var(--accent-violet); word-break:break-word; display:flex; align-items:flex-start; gap:6px; }
.msg-row.mine .msg-bubble { background:rgba(34,211,238,0.06); border-left:none; border-right:3px solid var(--accent-cyan); }
.msg-time { font-size:10px; color:var(--text-muted); margin-top:2px; font-family:var(--font-mono); }
.typing-row { opacity:0.7; }
.typing-bubble { gap:4px; padding:10px 14px; border-left-color:rgba(167,139,250,0.4); min-width:52px; }
.typing-dot { display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--accent-violet); animation:typing-bounce 1.2s infinite; }
.typing-dot:nth-child(2) { animation-delay:0.2s; }
.typing-dot:nth-child(3) { animation-delay:0.4s; }
@keyframes typing-bounce { 0%,60%,100% { transform:translateY(0); opacity:0.5; } 30% { transform:translateY(-4px); opacity:1; } }
.readonly-hint { padding:10px 12px; border-top:1px solid var(--border-dim); font-size:12px; color:var(--text-muted); text-align:center; }
.chat-input { display:flex; gap:8px; padding-top:10px; border-top:1px solid var(--accent-cyan); box-shadow:0 -2px 8px rgba(34,211,238,0.08); }
.chat-input .el-input { flex:1; }
.chat-input :deep(.el-input__wrapper) { background:var(--bg-card) !important; border-color:var(--border-dim) !important; box-shadow:none !important; }
.chat-input :deep(.el-input__wrapper:focus-within) { border-color:var(--accent-cyan) !important; box-shadow:0 0 8px rgba(34,211,238,0.15) !important; }
.chat-input :deep(.el-input__inner) { color:var(--text-primary) !important; font-family:var(--font-body); }
.chat-input .cyber-btn:disabled { opacity:0.4; cursor:not-allowed; }
</style>
