/**
 * 公司地图配置数据
 * Canvas尺寸: 600 x 600 (缩放后显示)
 * 多楼层: 每层 600x600，3个房间横向排列
 */

export interface RoomConfig {
  id: number
  name: string
  type: string
  department: string
  x: number
  y: number
  width: number
  height: number
  color: string
  labelColor: string
  floor: number
}

export const CANVAS_WIDTH = 600
export const CANVAS_HEIGHT = 600

/**
 * 楼层Y坐标编码偏移量。
 * pos_y = canvas_y + (floor - 1) * FLOOR_Y_OFFSET
 * 解码：canvas_y = pos_y % FLOOR_Y_OFFSET，floor = Math.floor(pos_y / FLOOR_Y_OFFSET) + 1
 * floor1: pos_y ∈ [0, 699]  floor2: pos_y ∈ [700, 1399]  floor3: pos_y ∈ [1400, 2099]
 */
export const FLOOR_Y_OFFSET = 700

export const FLOOR_LABELS: Record<number, string> = {
  1: '1F 大厅层',
  2: '2F 办公层',
  3: '3F 管理层',
}

export const ROOMS: RoomConfig[] = [
  // ── 1F 大厅层 ──
  { id: 1, name: '大厅', type: 'lounge', department: 'general',
    x: 20, y: 60, width: 260, height: 220, color: '#eef2ff', labelColor: '#374151', floor: 1 },
  { id: 2, name: '咖啡厅', type: 'cafeteria', department: 'general',
    x: 320, y: 60, width: 260, height: 220, color: '#fff7ed', labelColor: '#9a3412', floor: 1 },
  { id: 3, name: 'HR部门', type: 'office', department: 'hr',
    x: 20, y: 340, width: 560, height: 220, color: '#faf5ff', labelColor: '#6b21a8', floor: 1 },
  // ── 2F 办公层 ──
  // 左列(全高): 工程部 | 中列: 市场部(上)/产品部(下) | 右列: 财务部(上)/运营部(下)
  { id: 4, name: '工程部', type: 'office', department: 'engineering',
    x: 20, y: 60, width: 155, height: 280, color: '#eef2ff', labelColor: '#3730a3', floor: 2 },
  { id: 5, name: '市场部', type: 'office', department: 'marketing',
    x: 185, y: 60, width: 175, height: 130, color: '#fdf2f8', labelColor: '#9d174d', floor: 2 },
  { id: 6, name: '产品部', type: 'office', department: 'product',
    x: 185, y: 200, width: 175, height: 140, color: '#f0fdf4', labelColor: '#166534', floor: 2 },
  { id: 7, name: '财务部', type: 'office', department: 'finance',
    x: 370, y: 60, width: 170, height: 130, color: '#ecfdf5', labelColor: '#065f46', floor: 2 },
  { id: 8, name: '运营部', type: 'office', department: 'operations',
    x: 370, y: 200, width: 170, height: 140, color: '#fff7ed', labelColor: '#9a3412', floor: 2 },
  // ── 3F 管理层 ──
  { id: 9, name: '会议室', type: 'meeting', department: 'general',
    x: 20, y: 60, width: 560, height: 160, color: '#eff6ff', labelColor: '#1e40af', floor: 3 },
  { id: 10, name: '总监办公室', type: 'office', department: 'management',
    x: 20, y: 280, width: 260, height: 260, color: '#fffbeb', labelColor: '#92400e', floor: 3 },
  { id: 11, name: 'CEO办公室', type: 'ceo_office', department: 'management',
    x: 320, y: 280, width: 260, height: 260, color: '#fefce8', labelColor: '#854d0e', floor: 3 },
]

/** Room icon emoji for decoration */
export const ROOM_ICONS: Record<string, string> = {
  lounge: '🛋️',
  cafeteria: '☕',
  office: '💼',
  meeting: '📋',
  ceo_office: '👔',
}

/** Room furniture layout per type (relative positions inside room) */
export interface FurnitureItem {
  type: 'desk' | 'chair' | 'plant' | 'sofa' | 'table' | 'screen' | 'bookshelf' | 'coffee_machine'
  rx: number  // relative x ratio (0-1) within room
  ry: number  // relative y ratio (0-1) within room
}

export const ROOM_FURNITURE: Record<string, FurnitureItem[]> = {
  lounge: [
    { type: 'sofa', rx: 0.25, ry: 0.45 },
    { type: 'sofa', rx: 0.75, ry: 0.45 },
    { type: 'table', rx: 0.5, ry: 0.45 },
    { type: 'plant', rx: 0.1, ry: 0.15 },
    { type: 'plant', rx: 0.9, ry: 0.15 },
  ],
  cafeteria: [
    { type: 'table', rx: 0.25, ry: 0.4 },
    { type: 'table', rx: 0.75, ry: 0.4 },
    { type: 'table', rx: 0.25, ry: 0.7 },
    { type: 'table', rx: 0.75, ry: 0.7 },
    { type: 'coffee_machine', rx: 0.5, ry: 0.15 },
  ],
  office: [
    { type: 'desk', rx: 0.2, ry: 0.35 },
    { type: 'desk', rx: 0.5, ry: 0.35 },
    { type: 'desk', rx: 0.8, ry: 0.35 },
    { type: 'desk', rx: 0.2, ry: 0.65 },
    { type: 'desk', rx: 0.5, ry: 0.65 },
    { type: 'desk', rx: 0.8, ry: 0.65 },
    { type: 'plant', rx: 0.05, ry: 0.12 },
  ],
  meeting: [
    { type: 'table', rx: 0.5, ry: 0.5 },
    { type: 'chair', rx: 0.25, ry: 0.35 },
    { type: 'chair', rx: 0.75, ry: 0.35 },
    { type: 'chair', rx: 0.25, ry: 0.65 },
    { type: 'chair', rx: 0.75, ry: 0.65 },
    { type: 'screen', rx: 0.5, ry: 0.12 },
  ],
  ceo_office: [
    { type: 'desk', rx: 0.5, ry: 0.35 },
    { type: 'bookshelf', rx: 0.1, ry: 0.12 },
    { type: 'bookshelf', rx: 0.9, ry: 0.12 },
    { type: 'sofa', rx: 0.3, ry: 0.75 },
    { type: 'plant', rx: 0.85, ry: 0.75 },
  ],
}

/** 按楼层筛选房间 */
export function getRoomsByFloor(floor: number): RoomConfig[] {
  return ROOMS.filter(r => r.floor === floor)
}

export const CAREER_LEVELS: Record<number, { title: string; tasksRequired: number; xpRequired: number }> = {
  0: { title: '实习生', tasksRequired: 0, xpRequired: 0 },
  1: { title: '初级员工', tasksRequired: 5, xpRequired: 100 },
  2: { title: '中级员工', tasksRequired: 15, xpRequired: 350 },
  3: { title: '高级员工', tasksRequired: 30, xpRequired: 800 },
  4: { title: '经理', tasksRequired: 50, xpRequired: 1500 },
  5: { title: '总监', tasksRequired: 80, xpRequired: 3000 },
  6: { title: 'CEO', tasksRequired: 120, xpRequired: 5000 },
}

/** 双轨职业路径（Lv.4+）*/
export const CAREER_PATHS: Record<string, Record<number, { title: string }>> = {
  management: {
    4: { title: '经理' },
    5: { title: '总监' },
    6: { title: 'CEO' },
  },
  technical: {
    4: { title: '技术专家' },
    5: { title: '首席工程师' },
    6: { title: 'CTO' },
  },
}

export function getCareerTitle(level: number, path: string = 'management'): string {
  if (level < 4) return CAREER_LEVELS[level]?.title || '未知'
  return CAREER_PATHS[path]?.[level]?.title || CAREER_LEVELS[level]?.title || '未知'
}

export const DEPARTMENTS: Record<string, string> = {
  management: '管理层',
  engineering: '工程部',
  product: '产品部',
  marketing: '市场部',
  finance: '财务部',
  hr: 'HR部门',
  operations: '运营部',
  general: '公共区域',
  unassigned: '未分配',
}

/** 用户可选择加入的业务部门（排除公共区域和未分配） */
export const SELECTABLE_DEPARTMENTS: Record<string, string> = {
  engineering: '工程部',
  product: '产品部',
  marketing: '市场部',
  finance: '财务部',
  hr: 'HR部门',
  operations: '运营部',
}

export const MBTI_TYPES = [
  'INTJ', 'INTP', 'ENTJ', 'ENTP',
  'INFJ', 'INFP', 'ENFJ', 'ENFP',
  'ISTJ', 'ISFJ', 'ESTJ', 'ESFJ',
  'ISTP', 'ISFP', 'ESTP', 'ESFP',
]

export const AVATAR_KEYS = [
  'default', 'avatar1', 'avatar2', 'avatar3', 'avatar4',
  'avatar5', 'avatar6', 'avatar7', 'avatar8',
]

export const ACTION_LABELS: Record<string, string> = {
  idle: '空闲',
  working: '工作中',
  moving: '移动中',
  chatting: '聊天中',
  resting: '休息中',
  meeting: '会议中',
  work: '工作中',
  chat: '聊天中',
  rest: '休息中',
}

/**
 * 语义化座位定义（与 app/engine/named_spots.py 完全对齐）
 * spot_type:
 *   anchor   - 高管锚定位（CEO/总监专属）
 *   work     - 普通工位
 *   visitor  - 访客席（在高管办公室前）
 *   rest     - 休息区（咖啡厅/大厅）
 *   meeting  - 会议室座椅
 *   reception- 大厅前台
 */
export type SpotType = 'anchor' | 'work' | 'visitor' | 'rest' | 'meeting' | 'reception'

export interface NamedSpot {
  x: number
  y: number   // canvas y (before floor encoding)
  floor: number
  dept: string
  spot_type: SpotType
}

/** 座位类型对应的视觉颜色 */
export const SPOT_COLORS: Record<SpotType, string> = {
  anchor:    '#f59e0b',  // 金黄 — 高管专属
  work:      '#22d3ee',  // 青色 — 工位
  visitor:   '#a78bfa',  // 紫色 — 访客席
  rest:      '#fb923c',  // 橙色 — 休息区
  meeting:   '#4ade80',  // 绿色 — 会议椅
  reception: '#f472b6',  // 粉色 — 前台
}

export const NAMED_SPOTS: Record<string, NamedSpot> = {
  // 1F 大厅
  lobby_reception:  { x: 150, y: 72,  floor: 1, dept: 'general',    spot_type: 'reception' },
  lobby_sofa_left:  { x: 85,  y: 176, floor: 1, dept: 'general',    spot_type: 'rest' },
  lobby_sofa_right: { x: 215, y: 176, floor: 1, dept: 'general',    spot_type: 'rest' },
  lobby_table:      { x: 150, y: 176, floor: 1, dept: 'general',    spot_type: 'rest' },
  // 1F 咖啡厅
  cafe_counter:  { x: 450, y: 118, floor: 1, dept: 'general', spot_type: 'rest' },
  cafe_table_1:  { x: 385, y: 166, floor: 1, dept: 'general', spot_type: 'rest' },
  cafe_table_2:  { x: 515, y: 166, floor: 1, dept: 'general', spot_type: 'rest' },
  cafe_table_3:  { x: 385, y: 223, floor: 1, dept: 'general', spot_type: 'rest' },
  cafe_table_4:  { x: 515, y: 223, floor: 1, dept: 'general', spot_type: 'rest' },
  // 1F HR
  hr_desk_1: { x: 132, y: 436, floor: 1, dept: 'hr', spot_type: 'work' },
  hr_desk_2: { x: 300, y: 436, floor: 1, dept: 'hr', spot_type: 'work' },
  hr_desk_3: { x: 468, y: 436, floor: 1, dept: 'hr', spot_type: 'work' },
  hr_desk_4: { x: 132, y: 493, floor: 1, dept: 'hr', spot_type: 'work' },
  hr_desk_5: { x: 300, y: 493, floor: 1, dept: 'hr', spot_type: 'work' },
  hr_desk_6: { x: 468, y: 493, floor: 1, dept: 'hr', spot_type: 'work' },
  hr_interview: { x: 300, y: 514, floor: 1, dept: 'hr', spot_type: 'visitor' },
  // 2F 工程部
  eng_desk_1: { x: 51,  y: 177, floor: 2, dept: 'engineering', spot_type: 'work' },
  eng_desk_2: { x: 97,  y: 177, floor: 2, dept: 'engineering', spot_type: 'work' },
  eng_desk_3: { x: 144, y: 177, floor: 2, dept: 'engineering', spot_type: 'work' },
  eng_desk_4: { x: 51,  y: 252, floor: 2, dept: 'engineering', spot_type: 'work' },
  eng_desk_5: { x: 97,  y: 252, floor: 2, dept: 'engineering', spot_type: 'work' },
  eng_desk_6: { x: 144, y: 252, floor: 2, dept: 'engineering', spot_type: 'work' },
  // 2F 市场部
  marketing_desk_1: { x: 220, y: 125, floor: 2, dept: 'marketing', spot_type: 'work' },
  marketing_desk_2: { x: 272, y: 125, floor: 2, dept: 'marketing', spot_type: 'work' },
  marketing_desk_3: { x: 325, y: 125, floor: 2, dept: 'marketing', spot_type: 'work' },
  marketing_desk_4: { x: 220, y: 155, floor: 2, dept: 'marketing', spot_type: 'work' },
  marketing_desk_5: { x: 272, y: 155, floor: 2, dept: 'marketing', spot_type: 'work' },
  marketing_desk_6: { x: 325, y: 155, floor: 2, dept: 'marketing', spot_type: 'work' },
  // 2F 产品部
  product_desk_1: { x: 220, y: 268, floor: 2, dept: 'product', spot_type: 'work' },
  product_desk_2: { x: 272, y: 268, floor: 2, dept: 'product', spot_type: 'work' },
  product_desk_3: { x: 325, y: 268, floor: 2, dept: 'product', spot_type: 'work' },
  product_desk_4: { x: 220, y: 301, floor: 2, dept: 'product', spot_type: 'work' },
  product_desk_5: { x: 272, y: 301, floor: 2, dept: 'product', spot_type: 'work' },
  product_desk_6: { x: 325, y: 301, floor: 2, dept: 'product', spot_type: 'work' },
  // 2F 财务部
  finance_desk_1: { x: 404, y: 125, floor: 2, dept: 'finance', spot_type: 'work' },
  finance_desk_2: { x: 455, y: 125, floor: 2, dept: 'finance', spot_type: 'work' },
  finance_desk_3: { x: 506, y: 125, floor: 2, dept: 'finance', spot_type: 'work' },
  finance_desk_4: { x: 404, y: 155, floor: 2, dept: 'finance', spot_type: 'work' },
  finance_desk_5: { x: 455, y: 155, floor: 2, dept: 'finance', spot_type: 'work' },
  finance_desk_6: { x: 506, y: 155, floor: 2, dept: 'finance', spot_type: 'work' },
  // 2F 运营部
  ops_desk_1: { x: 404, y: 268, floor: 2, dept: 'operations', spot_type: 'work' },
  ops_desk_2: { x: 455, y: 268, floor: 2, dept: 'operations', spot_type: 'work' },
  ops_desk_3: { x: 506, y: 268, floor: 2, dept: 'operations', spot_type: 'work' },
  ops_desk_4: { x: 404, y: 301, floor: 2, dept: 'operations', spot_type: 'work' },
  ops_desk_5: { x: 455, y: 301, floor: 2, dept: 'operations', spot_type: 'work' },
  ops_desk_6: { x: 506, y: 301, floor: 2, dept: 'operations', spot_type: 'work' },
  // 3F 会议室
  meeting_chair_1: { x: 160, y: 135, floor: 3, dept: 'general', spot_type: 'meeting' },
  meeting_chair_2: { x: 240, y: 135, floor: 3, dept: 'general', spot_type: 'meeting' },
  meeting_chair_3: { x: 340, y: 135, floor: 3, dept: 'general', spot_type: 'meeting' },
  meeting_chair_4: { x: 440, y: 135, floor: 3, dept: 'general', spot_type: 'meeting' },
  meeting_chair_5: { x: 160, y: 175, floor: 3, dept: 'general', spot_type: 'meeting' },
  meeting_chair_6: { x: 240, y: 175, floor: 3, dept: 'general', spot_type: 'meeting' },
  meeting_chair_7: { x: 340, y: 175, floor: 3, dept: 'general', spot_type: 'meeting' },
  meeting_chair_8: { x: 440, y: 175, floor: 3, dept: 'general', spot_type: 'meeting' },
  // 3F 总监办公室
  director_desk:      { x: 150, y: 390, floor: 3, dept: 'management', spot_type: 'anchor' },
  director_visitor_1: { x: 72,  y: 459, floor: 3, dept: 'management', spot_type: 'visitor' },
  director_visitor_2: { x: 150, y: 459, floor: 3, dept: 'management', spot_type: 'visitor' },
  director_visitor_3: { x: 228, y: 459, floor: 3, dept: 'management', spot_type: 'visitor' },
  // 3F CEO办公室
  ceo_desk:      { x: 450, y: 390, floor: 3, dept: 'management', spot_type: 'anchor' },
  ceo_sofa:      { x: 398, y: 482, floor: 3, dept: 'management', spot_type: 'visitor' },
  ceo_visitor_1: { x: 450, y: 482, floor: 3, dept: 'management', spot_type: 'visitor' },
  ceo_visitor_2: { x: 500, y: 482, floor: 3, dept: 'management', spot_type: 'visitor' },
}

export const AVATAR_COLORS: Record<string, string> = {
  default: '#6366f1',
  avatar1: '#ec4899',
  avatar2: '#f59e0b',
  avatar3: '#10b981',
  avatar4: '#3b82f6',
  avatar5: '#8b5cf6',
  avatar6: '#ef4444',
  avatar7: '#14b8a6',
  avatar8: '#f97316',
}
