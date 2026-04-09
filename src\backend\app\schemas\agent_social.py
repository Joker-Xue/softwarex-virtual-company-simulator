"""
虚拟Agent社交系统 - Pydantic Schemas
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

from app.utils.sanitize import validate_mbti, sanitize_text


# ── 晋升体系常量 ──
CAREER_LEVELS = {
    0: {"title": "实习生", "tasks_required": 0, "xp_required": 0},
    1: {"title": "初级员工", "tasks_required": 5, "xp_required": 100},
    2: {"title": "中级员工", "tasks_required": 15, "xp_required": 350},
    3: {"title": "高级员工", "tasks_required": 30, "xp_required": 800},
    4: {"title": "经理", "tasks_required": 50, "xp_required": 1500},
    5: {"title": "总监", "tasks_required": 80, "xp_required": 3000},
    6: {"title": "CEO", "tasks_required": 120, "xp_required": 5000},
}

DEPARTMENTS = ["engineering", "marketing", "finance", "hr"]

# 双轨制职业路径（Lv.4+）
CAREER_PATHS = {
    "management": {
        4: {"title": "经理", "tasks_required": 50, "xp_required": 1500, "bonus_attrs": ["leadership", "communication"]},
        5: {"title": "总监", "tasks_required": 80, "xp_required": 3000, "bonus_attrs": ["leadership", "communication"]},
        6: {"title": "CEO", "tasks_required": 120, "xp_required": 5000, "bonus_attrs": ["leadership", "communication"]},
    },
    "technical": {
        4: {"title": "技术专家", "tasks_required": 50, "xp_required": 1500, "bonus_attrs": ["technical", "creativity"]},
        5: {"title": "首席工程师", "tasks_required": 80, "xp_required": 3000, "bonus_attrs": ["technical", "creativity"]},
        6: {"title": "CTO", "tasks_required": 120, "xp_required": 5000, "bonus_attrs": ["technical", "creativity"]},
    },
}


def get_career_title(level: int, career_path: str = "management") -> str:
    """根据等级和职业路径获取职称"""
    if level < 4:
        return CAREER_LEVELS.get(level, {}).get("title", "未知")
    path_data = CAREER_PATHS.get(career_path, CAREER_PATHS["management"])
    return path_data.get(level, {}).get("title", CAREER_LEVELS.get(level, {}).get("title", "未知"))


# ── AgentProfile ──
class AgentProfileCreate(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=50, pattern=r'^[^<>&"\'\/\\]+$')
    mbti: str = Field(..., min_length=4, max_length=4)
    avatar_key: str = "default"
    personality: List[str] = []
    attr_communication: int = Field(50, ge=0, le=100)
    attr_leadership: int = Field(50, ge=0, le=100)
    attr_creativity: int = Field(50, ge=0, le=100)
    attr_technical: int = Field(50, ge=0, le=100)
    attr_teamwork: int = Field(50, ge=0, le=100)
    attr_diligence: int = Field(50, ge=0, le=100)
    department: str = "engineering"

    @field_validator('mbti')
    @classmethod
    def check_mbti(cls, v: str) -> str:
        return validate_mbti(v)

    @field_validator('nickname')
    @classmethod
    def check_nickname(cls, v: str) -> str:
        return sanitize_text(v)


class AgentProfileUpdate(BaseModel):
    nickname: Optional[str] = None
    avatar_key: Optional[str] = None
    personality: Optional[List[str]] = None
    ai_enabled: Optional[bool] = None


class ScheduleEntry(BaseModel):
    time: str
    activity: str
    room_type: str


class AgentProfileOut(BaseModel):
    id: int
    user_id: int
    nickname: str
    avatar_key: str
    mbti: str
    personality: List[str]
    attr_communication: int
    attr_leadership: int
    attr_creativity: int
    attr_technical: int
    attr_teamwork: int
    attr_diligence: int
    career_level: int
    career_title: str = ""
    department: str
    tasks_completed: int
    xp: int
    pos_x: int
    pos_y: int
    current_action: str
    is_online: bool
    ai_enabled: bool
    daily_schedule: List[ScheduleEntry] = []
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── InteriorObject ──
class InteriorObject(BaseModel):
    type: str
    name: str
    x: float
    y: float
    width: float
    height: float
    interactive: bool = False


# ── CompanyRoom ──
class CompanyRoomOut(BaseModel):
    id: int
    name: str
    room_type: str
    department: str
    x: int
    y: int
    width: int
    height: int
    capacity: int
    floor: int = 1
    interior_objects: List[InteriorObject] = []
    description: Optional[str] = None

    @field_validator("floor", mode="before")
    @classmethod
    def coerce_floor(cls, v):
        return v if v is not None else 1

    @field_validator("interior_objects", mode="before")
    @classmethod
    def coerce_interior_objects(cls, v):
        return v if v is not None else []

    class Config:
        from_attributes = True


# ── AgentTask ──
class TaskAssign(BaseModel):
    assignee_id: int
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    difficulty: int = Field(1, ge=1, le=5)
    task_type: str = "project"


class TaskOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    task_type: str
    difficulty: int
    xp_reward: int
    assigner_id: Optional[int]
    assignee_id: int
    status: str
    deadline: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Friendship ──
class FriendshipOut(BaseModel):
    id: int
    from_id: int
    to_id: int
    status: str
    created_at: Optional[datetime]
    accepted_at: Optional[datetime]
    friend_nickname: str = ""
    friend_avatar: str = ""
    friend_level: int = 0
    friend_department: str = ""
    friend_mbti: str = ""
    affinity: int = 50
    compatibility_score: float = 0.0
    compatibility_label: str = ""
    role: str = ""  # "mentor" / "mentee" / ""

    class Config:
        from_attributes = True


class CompatibilityDetail(BaseModel):
    friend_id: int
    friend_nickname: str = ""
    mbti_a: str
    mbti_b: str
    compatibility_score: float
    compatibility_label: str
    tips: str
    role: str = ""  # "mentor" / "mentee" / ""


# ── Message ──
class MessageSend(BaseModel):
    receiver_id: int
    content: str = Field(..., min_length=1, max_length=2000)

    @field_validator('content')
    @classmethod
    def check_content(cls, v: str) -> str:
        return sanitize_text(v)


class MessageOut(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    content: str
    msg_type: str
    is_read: bool
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Move ──
class MoveRequest(BaseModel):
    x: int = Field(..., ge=0, le=600)
    y: int = Field(..., ge=0, le=2099)


class InteractionSpot(BaseModel):
    id: str
    name: str
    x: int
    y: int
    floor: int
    spot_type: str
    room_id: int


class ObjectAction(BaseModel):
    object_key: str
    action_key: str
    action_type: str
    task_tags: List[str] = []
    cooldown_sec: int
    duration_sec: int


class ObjectOccupancy(BaseModel):
    object_key: str
    occupant_agent_id: Optional[int] = None
    lock_until: Optional[str] = None
    queue_count: int = 0


class RoomInteractionsOut(BaseModel):
    room_id: int
    interaction_spots: List[InteractionSpot]
    object_actions: List[ObjectAction]
    occupancies: List[ObjectOccupancy]
    metrics: dict = {}


class MoveInsideRequest(BaseModel):
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)


class MoveInsideOut(BaseModel):
    room_id: int
    spot: InteractionSpot
    pos_x: int
    pos_y: int


class InteractRequest(BaseModel):
    object_key: str


class InteractResult(BaseModel):
    success: bool
    reason: str
    task_delta: int = 0
    xp_delta: int = 0
    level_up: bool = False
    cooldown_left_sec: int = 0
    queue_count: int = 0
    occupancy: Optional[ObjectOccupancy] = None


# ── Leaderboard ──
class LeaderboardEntry(BaseModel):
    agent_id: int
    nickname: str
    avatar_key: str
    career_level: int
    career_title: str
    xp: int
    tasks_completed: int
    department: str


# ── Achievement ──
class AchievementOut(BaseModel):
    id: int
    key: str
    name: str
    description: str
    category: str
    icon: str
    coin_reward: int
    is_unlocked: bool = False
    unlocked_at: Optional[datetime] = None
    progress: float = 0.0  # 0.0 to 1.0

    class Config:
        from_attributes = True
