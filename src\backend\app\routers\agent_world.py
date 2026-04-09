"""
地图与世界API
"""
import time
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db
from app.utils.security import get_current_active_user
from app.models.user import User
from app.models.agent_profile import AgentProfile
from app.models.company_room import CompanyRoom
from app.models.agent_task import AgentTask
from app.models.coin_wallet import CoinWallet, CoinTransaction
from app.schemas.agent_social import (
    CompanyRoomOut, MoveRequest, AgentProfileOut, CAREER_LEVELS,
    InteractionSpot, ObjectAction, ObjectOccupancy, RoomInteractionsOut,
    MoveInsideRequest, MoveInsideOut, InteractRequest, InteractResult,
)
from app.engine.named_spots import snap_to_nearest_spot, get_spot_pos
from app.engine.task_generator import generate_tasks_for_agent
from app.engine.achievement_engine import check_achievements
from app.routers.agent_task import complete_task_internal

router = APIRouter()

_OBJECT_TASK_MAP: dict[str, dict[str, Any]] = {
    "computer": {"action_key": "focus_work", "action_type": "work", "task_tags": ["technical", "work"], "cooldown_sec": 15, "duration_sec": 12},
    "desk": {"action_key": "desk_work", "action_type": "work", "task_tags": ["work"], "cooldown_sec": 12, "duration_sec": 10},
    "coffee_machine": {"action_key": "coffee_break", "action_type": "rest", "task_tags": ["social", "rest"], "cooldown_sec": 10, "duration_sec": 8},
    "bar_counter": {"action_key": "social_talk", "action_type": "social", "task_tags": ["social", "rest"], "cooldown_sec": 10, "duration_sec": 8},
    "whiteboard": {"action_key": "whiteboard_review", "action_type": "meeting", "task_tags": ["meeting", "presentation"], "cooldown_sec": 14, "duration_sec": 10},
    "presentation_screen": {"action_key": "present_plan", "action_type": "presentation", "task_tags": ["meeting", "presentation"], "cooldown_sec": 14, "duration_sec": 10},
    "projector_screen": {"action_key": "projector_sync", "action_type": "presentation", "task_tags": ["meeting", "presentation"], "cooldown_sec": 14, "duration_sec": 10},
    "filing_cabinet": {"action_key": "file_review", "action_type": "management", "task_tags": ["management", "finance"], "cooldown_sec": 12, "duration_sec": 9},
    "calculator_station": {"action_key": "finance_calc", "action_type": "finance", "task_tags": ["management", "finance"], "cooldown_sec": 12, "duration_sec": 9},
    "safe": {"action_key": "asset_check", "action_type": "finance", "task_tags": ["finance"], "cooldown_sec": 12, "duration_sec": 9},
    "mood_board": {"action_key": "idea_brainstorm", "action_type": "planning", "task_tags": ["creative", "presentation"], "cooldown_sec": 12, "duration_sec": 9},
    "vending_machine": {"action_key": "snack_break", "action_type": "rest", "task_tags": ["rest"], "cooldown_sec": 10, "duration_sec": 8},
}

_OCCUPANCY: dict[str, dict[str, Any]] = {}
_INTERACTION_METRICS: dict[int, dict[str, Any]] = defaultdict(
    lambda: {
        "interactions_total": 0,
        "success_total": 0,
        "fail_total": 0,
        "fail_reasons": defaultdict(int),
        "queue_wait_total_sec": 0.0,
        "queue_wait_count": 0,
    }
)


def _room_object_key(room_id: int, object_key: str) -> str:
    return f"{room_id}:{object_key}"


def _cleanup_occupancy(now: float):
    for k, v in list(_OCCUPANCY.items()):
        lock_until = float(v.get("lock_until", 0))
        if lock_until <= now:
            _OCCUPANCY.pop(k, None)


def _to_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _record_metric(room_id: int, success: bool, reason: str = "", queue_wait: float | None = None):
    m = _INTERACTION_METRICS[room_id]
    m["interactions_total"] += 1
    if success:
        m["success_total"] += 1
    else:
        m["fail_total"] += 1
        if reason:
            m["fail_reasons"][reason] += 1
    if queue_wait is not None and queue_wait >= 0:
        m["queue_wait_total_sec"] += queue_wait
        m["queue_wait_count"] += 1


def _metric_out(room_id: int) -> dict:
    m = _INTERACTION_METRICS[room_id]
    avg_wait = 0.0
    if m["queue_wait_count"] > 0:
        avg_wait = round(m["queue_wait_total_sec"] / m["queue_wait_count"], 3)
    return {
        "interactions_total": m["interactions_total"],
        "success_total": m["success_total"],
        "fail_total": m["fail_total"],
        "fail_reasons": dict(m["fail_reasons"]),
        "avg_wait_sec": avg_wait,
    }


def _spot_type_for_object(obj_type: str) -> str:
    if obj_type in {"desk", "computer", "server_rack", "safe", "calculator_station"}:
        return "work"
    if obj_type in {"coffee_machine", "bar_counter", "vending_machine", "sofa", "table"}:
        return "rest"
    if obj_type in {"whiteboard", "presentation_screen", "projector_screen"}:
        return "meeting"
    return "visitor"


def _build_interaction_spots(room: CompanyRoom) -> list[InteractionSpot]:
    spots: list[InteractionSpot] = []
    objects = room.interior_objects or []
    for idx, obj in enumerate(objects):
        try:
            cx = int(obj["x"] + obj["width"] / 2)
            cy = int(obj["y"] + obj["height"] / 2)
            spots.append(
                InteractionSpot(
                    id=f"{room.id}_obj_{idx}",
                    name=str(obj.get("name", f"物件{idx+1}")),
                    x=cx,
                    y=cy,
                    floor=room.floor or 1,
                    spot_type=_spot_type_for_object(str(obj.get("type", ""))),
                    room_id=room.id,
                )
            )
        except Exception:
            continue
    spots.append(
        InteractionSpot(
            id=f"{room.id}_center",
            name="房间中心",
            x=max(0, room.width // 2),
            y=max(0, room.height // 2),
            floor=room.floor or 1,
            spot_type="visitor",
            room_id=room.id,
        )
    )
    return spots


def _find_nearest_spot(spots: list[InteractionSpot], x: int, y: int) -> InteractionSpot:
    best = spots[0]
    best_d = 10**18
    for s in spots:
        dx = x - s.x
        dy = y - s.y
        d = dx * dx + dy * dy
        if d < best_d:
            best_d = d
            best = s
    return best


def _build_object_actions(room: CompanyRoom) -> list[ObjectAction]:
    actions: list[ObjectAction] = []
    for idx, obj in enumerate(room.interior_objects or []):
        if not obj.get("interactive"):
            continue
        cfg = _OBJECT_TASK_MAP.get(str(obj.get("type", "")))
        if not cfg:
            continue
        actions.append(
            ObjectAction(
                object_key=f"obj_{idx}",
                action_key=cfg["action_key"],
                action_type=cfg["action_type"],
                task_tags=list(cfg["task_tags"]),
                cooldown_sec=int(cfg["cooldown_sec"]),
                duration_sec=int(cfg["duration_sec"]),
            )
        )
    return actions


def _occupancy_for(room_id: int, action: ObjectAction) -> ObjectOccupancy:
    now = time.time()
    _cleanup_occupancy(now)
    k = _room_object_key(room_id, action.object_key)
    item = _OCCUPANCY.get(k)
    if not item:
        return ObjectOccupancy(object_key=action.object_key, occupant_agent_id=None, lock_until=None, queue_count=0)
    return ObjectOccupancy(
        object_key=action.object_key,
        occupant_agent_id=item.get("occupant_agent_id"),
        lock_until=_to_iso(item.get("lock_until")),
        queue_count=len(item.get("queue", [])),
    )

# 种子房间数据 — 多楼层布局
# 每层 600x600 画布，3个房间横向排列
# Room 1: x=0,   y=100, w=180, h=400
# Room 2: x=210, y=100, w=180, h=400
# Room 3: x=420, y=100, w=180, h=400
# interior_objects 坐标相对于房间内部 (0,0)-(180,400)
SEED_ROOMS = [
    # ── 1F 大厅层 ──
    {
        "name": "大厅", "room_type": "lounge", "department": "general",
        "x": 0, "y": 100, "width": 180, "height": 400, "capacity": 30,
        "floor": 1, "description": "公司中央大厅",
        "interior_objects": [
            {"type": "desk", "name": "前台接待桌", "x": 40, "y": 20, "width": 100, "height": 30, "interactive": True},
            {"type": "sofa", "name": "沙发A", "x": 10, "y": 100, "width": 60, "height": 30, "interactive": False},
            {"type": "sofa", "name": "沙发B", "x": 110, "y": 100, "width": 60, "height": 30, "interactive": False},
            {"type": "table", "name": "茶几", "x": 60, "y": 140, "width": 60, "height": 25, "interactive": False},
            {"type": "water_fountain", "name": "喷泉", "x": 65, "y": 220, "width": 50, "height": 50, "interactive": True},
            {"type": "info_board", "name": "信息公告栏", "x": 10, "y": 310, "width": 60, "height": 50, "interactive": True},
            {"type": "plant", "name": "绿植A", "x": 10, "y": 70, "width": 20, "height": 20, "interactive": False},
            {"type": "plant", "name": "绿植B", "x": 150, "y": 70, "width": 20, "height": 20, "interactive": False},
        ],
    },
    {
        "name": "咖啡厅", "room_type": "cafeteria", "department": "general",
        "x": 210, "y": 100, "width": 180, "height": 400, "capacity": 25,
        "floor": 1, "description": "休息与社交区域",
        "interior_objects": [
            {"type": "table", "name": "餐桌1", "x": 15, "y": 30, "width": 50, "height": 35, "interactive": False},
            {"type": "table", "name": "餐桌2", "x": 110, "y": 30, "width": 50, "height": 35, "interactive": False},
            {"type": "table", "name": "餐桌3", "x": 15, "y": 120, "width": 50, "height": 35, "interactive": False},
            {"type": "table", "name": "餐桌4", "x": 110, "y": 120, "width": 50, "height": 35, "interactive": False},
            {"type": "coffee_machine", "name": "咖啡机", "x": 130, "y": 220, "width": 35, "height": 30, "interactive": True},
            {"type": "vending_machine", "name": "自动售货机", "x": 130, "y": 270, "width": 35, "height": 45, "interactive": True},
            {"type": "bar_counter", "name": "吧台", "x": 20, "y": 230, "width": 90, "height": 25, "interactive": True},
            {"type": "plant", "name": "绿植A", "x": 10, "y": 340, "width": 20, "height": 20, "interactive": False},
            {"type": "plant", "name": "绿植B", "x": 80, "y": 340, "width": 20, "height": 20, "interactive": False},
        ],
    },
    {
        "name": "HR部门", "room_type": "office", "department": "hr",
        "x": 420, "y": 100, "width": 180, "height": 400, "capacity": 15,
        "floor": 1, "description": "人力资源团队办公区",
        "interior_objects": [
            {"type": "desk", "name": "工位1", "x": 15, "y": 40, "width": 60, "height": 30, "interactive": True},
            {"type": "desk", "name": "工位2", "x": 15, "y": 100, "width": 60, "height": 30, "interactive": True},
            {"type": "desk", "name": "工位3", "x": 105, "y": 40, "width": 60, "height": 30, "interactive": True},
            {"type": "interview_booth", "name": "面试间", "x": 95, "y": 140, "width": 70, "height": 60, "interactive": True},
            {"type": "filing_cabinet", "name": "档案柜A", "x": 10, "y": 240, "width": 30, "height": 55, "interactive": True},
            {"type": "filing_cabinet", "name": "档案柜B", "x": 55, "y": 240, "width": 30, "height": 55, "interactive": True},
            {"type": "notice_board", "name": "公告栏", "x": 60, "y": 10, "width": 60, "height": 20, "interactive": True},
        ],
    },
    # ── 2F 办公层 ──
    # 左列(全高): 工程部  | 中列: 市场部(上)/产品部(下) | 右列: 财务部(上)/运营部(下)
    {
        "name": "工程部", "room_type": "office", "department": "engineering",
        "x": 0, "y": 50, "width": 200, "height": 450, "capacity": 20,
        "floor": 2, "description": "工程技术团队办公区",
        "interior_objects": [
            {"type": "desk", "name": "工位1", "x": 10, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "computer", "name": "电脑1", "x": 20, "y": 43, "width": 18, "height": 14, "interactive": True},
            {"type": "desk", "name": "工位2", "x": 10, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "computer", "name": "电脑2", "x": 20, "y": 93, "width": 18, "height": 14, "interactive": True},
            {"type": "desk", "name": "工位3", "x": 10, "y": 140, "width": 60, "height": 28, "interactive": True},
            {"type": "computer", "name": "电脑3", "x": 20, "y": 143, "width": 18, "height": 14, "interactive": True},
            {"type": "desk", "name": "工位4", "x": 120, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "computer", "name": "电脑4", "x": 130, "y": 43, "width": 18, "height": 14, "interactive": True},
            {"type": "desk", "name": "工位5", "x": 120, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "computer", "name": "电脑5", "x": 130, "y": 93, "width": 18, "height": 14, "interactive": True},
            {"type": "desk", "name": "工位6", "x": 120, "y": 140, "width": 60, "height": 28, "interactive": True},
            {"type": "computer", "name": "电脑6", "x": 130, "y": 143, "width": 18, "height": 14, "interactive": True},
            {"type": "server_rack", "name": "服务器机架", "x": 75, "y": 260, "width": 50, "height": 60, "interactive": True},
            {"type": "whiteboard", "name": "白板", "x": 65, "y": 10, "width": 70, "height": 20, "interactive": True},
        ],
    },
    {
        "name": "市场部", "room_type": "office", "department": "marketing",
        "x": 220, "y": 50, "width": 180, "height": 210, "capacity": 12,
        "floor": 2, "description": "市场营销团队办公区",
        "interior_objects": [
            {"type": "desk", "name": "工位1", "x": 10, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "工位2", "x": 10, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "工位3", "x": 110, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "工位4", "x": 110, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "presentation_screen", "name": "演示屏幕", "x": 50, "y": 10, "width": 80, "height": 20, "interactive": True},
            {"type": "mood_board", "name": "灵感板", "x": 120, "y": 140, "width": 50, "height": 50, "interactive": True},
        ],
    },
    {
        "name": "产品部", "room_type": "office", "department": "product",
        "x": 220, "y": 280, "width": 180, "height": 220, "capacity": 12,
        "floor": 2, "description": "产品管理团队办公区",
        "interior_objects": [
            {"type": "desk", "name": "工位1", "x": 10, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "工位2", "x": 10, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "工位3", "x": 110, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "工位4", "x": 110, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "whiteboard", "name": "产品白板", "x": 50, "y": 10, "width": 80, "height": 20, "interactive": True},
            {"type": "presentation_screen", "name": "原型展示屏", "x": 10, "y": 150, "width": 70, "height": 50, "interactive": True},
        ],
    },
    {
        "name": "财务部", "room_type": "office", "department": "finance",
        "x": 420, "y": 50, "width": 180, "height": 210, "capacity": 10,
        "floor": 2, "description": "财务管理团队办公区",
        "interior_objects": [
            {"type": "desk", "name": "工位1", "x": 10, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "工位2", "x": 10, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "工位3", "x": 110, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "工位4", "x": 110, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "safe", "name": "保险柜", "x": 70, "y": 140, "width": 40, "height": 40, "interactive": True},
            {"type": "calculator_station", "name": "核算台", "x": 50, "y": 10, "width": 80, "height": 20, "interactive": True},
        ],
    },
    {
        "name": "运营部", "room_type": "office", "department": "operations",
        "x": 420, "y": 280, "width": 180, "height": 220, "capacity": 12,
        "floor": 2, "description": "运营增长团队办公区",
        "interior_objects": [
            {"type": "desk", "name": "工位1", "x": 10, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "工位2", "x": 10, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "工位3", "x": 110, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "工位4", "x": 110, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "presentation_screen", "name": "数据大屏", "x": 50, "y": 10, "width": 80, "height": 20, "interactive": True},
            {"type": "mood_board", "name": "运营看板", "x": 10, "y": 150, "width": 60, "height": 50, "interactive": True},
        ],
    },
    # ── 3F 管理层 ──
    {
        "name": "会议室", "room_type": "meeting", "department": "general",
        "x": 0, "y": 100, "width": 180, "height": 400, "capacity": 12,
        "floor": 3, "description": "大型会议室",
        "interior_objects": [
            {"type": "table", "name": "会议桌", "x": 30, "y": 100, "width": 120, "height": 60, "interactive": False},
            {"type": "chair", "name": "会议椅1", "x": 40, "y": 80, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "会议椅2", "x": 70, "y": 80, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "会议椅3", "x": 100, "y": 80, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "会议椅4", "x": 130, "y": 80, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "会议椅5", "x": 40, "y": 165, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "会议椅6", "x": 70, "y": 165, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "会议椅7", "x": 100, "y": 165, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "会议椅8", "x": 130, "y": 165, "width": 18, "height": 18, "interactive": False},
            {"type": "projector_screen", "name": "投影幕布", "x": 10, "y": 20, "width": 160, "height": 40, "interactive": True},
            {"type": "whiteboard", "name": "白板", "x": 30, "y": 260, "width": 120, "height": 50, "interactive": True},
        ],
    },
    {
        "name": "总监办公室", "room_type": "office", "department": "management",
        "x": 210, "y": 100, "width": 180, "height": 400, "capacity": 4,
        "floor": 3, "description": "总监级别办公区",
        "interior_objects": [
            {"type": "desk", "name": "总监办公桌", "x": 50, "y": 80, "width": 80, "height": 35, "interactive": True},
            {"type": "chair", "name": "办公椅A", "x": 65, "y": 125, "width": 22, "height": 22, "interactive": False},
            {"type": "chair", "name": "办公椅B", "x": 100, "y": 125, "width": 22, "height": 22, "interactive": False},
            {"type": "filing_cabinet", "name": "文件柜", "x": 10, "y": 20, "width": 30, "height": 55, "interactive": True},
            {"type": "whiteboard", "name": "白板", "x": 130, "y": 20, "width": 40, "height": 60, "interactive": True},
        ],
    },
    {
        "name": "CEO办公室", "room_type": "ceo_office", "department": "management",
        "x": 420, "y": 100, "width": 180, "height": 400, "capacity": 2,
        "floor": 3, "description": "公司最高决策者的办公室",
        "interior_objects": [
            {"type": "desk", "name": "行政办公桌", "x": 50, "y": 80, "width": 80, "height": 35, "interactive": True},
            {"type": "chair", "name": "真皮座椅", "x": 75, "y": 125, "width": 25, "height": 25, "interactive": False},
            {"type": "bookshelf", "name": "书架", "x": 10, "y": 15, "width": 30, "height": 90, "interactive": True},
            {"type": "plant", "name": "绿植", "x": 145, "y": 15, "width": 25, "height": 25, "interactive": False},
            {"type": "globe", "name": "地球仪", "x": 140, "y": 130, "width": 25, "height": 25, "interactive": True},
        ],
    },
]

ROOM_NAME_ALIASES = {
    "会议室": ["会议室A"],
}


def _fill_career_title(profile: AgentProfile) -> dict:
    data = {c.name: getattr(profile, c.name) for c in AgentProfile.__table__.columns}
    data["career_title"] = CAREER_LEVELS.get(profile.career_level, {}).get("title", "未知")
    # personality 可能是 dict（NPC标记）或 list，统一转为 list
    p = data.get("personality")
    if isinstance(p, dict):
        data["personality"] = list(p.get("tags", []))  # NPC: 取 tags 或空列表
    elif not isinstance(p, list):
        data["personality"] = []
    # daily_schedule: 过滤掉模拟引擎的内部条目（_sim_state, _decision_log）
    schedule = data.get("daily_schedule") or []
    if isinstance(schedule, list):
        data["daily_schedule"] = [
            s for s in schedule
            if isinstance(s, dict) and not s.get("_sim_state") and "_decision_log" not in s
        ]
    return data


def _is_npc_profile(profile: AgentProfile) -> bool:
    """兼容 personality 的历史结构，识别 NPC 角色。"""
    p = profile.personality
    if isinstance(p, dict):
        return bool(p.get("is_npc"))
    if isinstance(p, list):
        for item in p:
            if isinstance(item, dict) and item.get("is_npc"):
                return True
    return False


async def _ensure_all_rooms(db: AsyncSession):
    """Upsert-lite: 确保 SEED_ROOMS 中的所有房间存在于DB（缺少则新增，NULL字段则修补）。
    按名称匹配，修复旧DB中 floor/interior_objects 为 NULL 的行，避免重复插入。"""
    changed = 0
    for r in SEED_ROOMS:
        candidate_names = [r["name"], *ROOM_NAME_ALIASES.get(r["name"], [])]
        result = await db.execute(
            select(CompanyRoom).where(CompanyRoom.name.in_(candidate_names))
        )
        existing_rows = result.scalars().all()
        existing = existing_rows[0] if existing_rows else None
        if len(existing_rows) > 1:
            duplicate_ids = [row.id for row in existing_rows[1:]]
            await db.execute(delete(CompanyRoom).where(CompanyRoom.id.in_(duplicate_ids)))
            changed += len(duplicate_ids)
        if existing is None:
            db.add(CompanyRoom(**r))
            changed += 1
        else:
            # Canonicalize legacy aliases to avoid front/back contract mismatch.
            if existing.name != r["name"]:
                existing.name = r["name"]
                changed += 1

            # Patch NULL fields on stale rows (old schema had no floor/interior_objects)
            patched = False
            if existing.floor is None:
                existing.floor = r["floor"]
                patched = True
            if existing.interior_objects is None:
                existing.interior_objects = r.get("interior_objects", [])
                patched = True
            if patched:
                changed += 1
    if changed:
        await db.flush()
        # 清除房间中心缓存，保证修复后的房间被纳入下次模拟决策
        from app.engine.agent_ai import clear_room_cache
        clear_room_cache()
    return changed


@router.get("/map", response_model=list[CompanyRoomOut], summary="获取公司地图")
async def get_map(
    floor: Optional[int] = Query(None, description="楼层筛选，不传则返回所有楼层"),
    db: AsyncSession = Depends(get_db),
):
    # 确保所有房间存在（幂等，新环境全量创建，旧环境补充缺失房间）
    await _ensure_all_rooms(db)
    stmt = select(CompanyRoom)
    if floor is not None:
        stmt = stmt.where(CompanyRoom.floor == floor)
    result = await db.execute(stmt)
    rooms = result.scalars().all()
    return rooms


@router.get("/agents/online", response_model=list[AgentProfileOut], summary="获取在线角色")
async def get_online_agents(db: AsyncSession = Depends(get_db)):
    # “可见角色”策略：
    # 1) 所有在线真人/玩家
    # 2) 所有NPC（常驻世界，避免受 is_online 脏状态影响导致楼层空白）
    result = await db.execute(select(AgentProfile))
    all_agents = result.scalars().all()
    agents = [
        a for a in all_agents
        if a.is_online or _is_npc_profile(a)
    ]
    return [AgentProfileOut(**_fill_career_title(a)) for a in agents]


@router.post("/move", response_model=AgentProfileOut, summary="移动角色")
async def move_agent(
    body: MoveRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")

    snapped_spot = snap_to_nearest_spot(
        x=body.x,
        encoded_y=body.y,
        career_level=profile.career_level or 0,
        department=profile.department or "",
        career_path=profile.career_path or "",
    )
    snapped_x, snapped_y = get_spot_pos(snapped_spot)
    profile.pos_x = snapped_x
    profile.pos_y = snapped_y
    profile.current_action = "moving"
    await db.flush()
    await db.refresh(profile)
    return AgentProfileOut(**_fill_career_title(profile))


async def _get_user_profile_room(
    db: AsyncSession,
    user: User,
    room_id: int,
) -> tuple[AgentProfile, CompanyRoom]:
    profile = (await db.execute(select(AgentProfile).where(AgentProfile.user_id == user.id))).scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")
    room = (await db.execute(select(CompanyRoom).where(CompanyRoom.id == room_id))).scalar_one_or_none()
    if not room:
        raise HTTPException(404, "房间不存在")
    return profile, room


@router.get("/rooms/{room_id}/interactions", response_model=RoomInteractionsOut, summary="获取房间可交互结构")
async def get_room_interactions(
    room_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    _ = user
    room = (await db.execute(select(CompanyRoom).where(CompanyRoom.id == room_id))).scalar_one_or_none()
    if not room:
        raise HTTPException(404, "房间不存在")
    spots = _build_interaction_spots(room)
    actions = _build_object_actions(room)
    occupancies = [_occupancy_for(room.id, a) for a in actions]
    return RoomInteractionsOut(
        room_id=room.id,
        interaction_spots=spots,
        object_actions=actions,
        occupancies=occupancies,
        metrics=_metric_out(room.id),
    )


@router.post("/rooms/{room_id}/move-inside", response_model=MoveInsideOut, summary="室内移动到合法交互点")
async def move_inside_room(
    room_id: int,
    body: MoveInsideRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    profile, room = await _get_user_profile_room(db, user, room_id)
    spots = _build_interaction_spots(room)
    if not spots:
        raise HTTPException(400, "该房间没有可移动点位")
    clamped_x = max(0, min(int(body.x), room.width))
    clamped_y = max(0, min(int(body.y), room.height))
    spot = _find_nearest_spot(spots, clamped_x, clamped_y)
    floor = room.floor or 1
    profile.pos_x = room.x + spot.x
    profile.pos_y = room.y + spot.y + (floor - 1) * 700
    profile.current_action = "moving"
    await db.flush()
    return MoveInsideOut(
        room_id=room.id,
        spot=spot,
        pos_x=profile.pos_x,
        pos_y=profile.pos_y,
    )


@router.post("/rooms/{room_id}/interact", response_model=InteractResult, summary="执行房间物件交互并联动任务")
async def interact_in_room(
    room_id: int,
    body: InteractRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    profile, room = await _get_user_profile_room(db, user, room_id)
    actions = _build_object_actions(room)
    action = next((a for a in actions if a.object_key == body.object_key), None)
    if not action:
        _record_metric(room.id, False, "invalid_object")
        raise HTTPException(400, "无效或不可交互的物件")

    floor = room.floor or 1
    profile_canvas_y = profile.pos_y % 700
    if not (
        room.x <= profile.pos_x <= room.x + room.width
        and room.y <= profile_canvas_y <= room.y + room.height
        and (profile.pos_y // 700 + 1) == floor
    ):
        _record_metric(room.id, False, "not_in_room")
        return InteractResult(success=False, reason="请先进入该房间再操作", queue_count=0)

    now = time.time()
    _cleanup_occupancy(now)
    occ_key = _room_object_key(room.id, action.object_key)
    state = _OCCUPANCY.get(occ_key)
    if state and state.get("occupant_agent_id") != profile.id and float(state.get("lock_until", 0)) > now:
        queue = state.setdefault("queue", [])
        queue_item = {"agent_id": profile.id, "joined_at": now}
        if not any(q.get("agent_id") == profile.id for q in queue):
            queue.append(queue_item)
        cooldown_left = int(max(0, state["lock_until"] - now))
        _record_metric(room.id, False, "occupied")
        return InteractResult(
            success=False,
            reason="物件占用中，已加入队列",
            cooldown_left_sec=cooldown_left,
            queue_count=len(queue),
            occupancy=_occupancy_for(room.id, action),
        )

    queue_wait = None
    if state:
        for q in state.get("queue", []):
            if q.get("agent_id") == profile.id:
                queue_wait = now - float(q.get("joined_at", now))
                break

    _OCCUPANCY[occ_key] = {
        "occupant_agent_id": profile.id,
        "lock_until": now + action.duration_sec,
        "queue": [],
    }

    # Task binding: try to complete one matching pending/in_progress task.
    # If no tasks exist, generate daily tasks once to keep loop闭环可用。
    my_tasks = (await db.execute(
        select(AgentTask).where(
            AgentTask.assignee_id == profile.id,
            AgentTask.status.in_(["pending", "in_progress"]),
        ).order_by(AgentTask.created_at.asc())
    )).scalars().all()
    if not my_tasks:
        try:
            await generate_tasks_for_agent(profile, db)
            my_tasks = (await db.execute(
                select(AgentTask).where(
                    AgentTask.assignee_id == profile.id,
                    AgentTask.status.in_(["pending", "in_progress"]),
                ).order_by(AgentTask.created_at.asc())
            )).scalars().all()
        except Exception:
            my_tasks = []

    matched = None
    tags = [t.lower() for t in action.task_tags]
    for t in my_tasks:
        hay = f"{t.task_type or ''} {t.title or ''} {t.description or ''}".lower()
        if any(tag in hay for tag in tags):
            matched = t
            break
    if matched is None and my_tasks:
        matched = my_tasks[0]

    task_delta = 0
    xp_delta = 0
    level_up = False
    if matched:
        wallet = (await db.execute(select(CoinWallet).where(CoinWallet.user_id == user.id))).scalar_one_or_none()
        if wallet:
            wallet.balance += matched.xp_reward
            wallet.total_earned += matched.xp_reward
            db.add(CoinTransaction(
                user_id=user.id,
                amount=matched.xp_reward,
                type="earn",
                source="room_interact",
                description=f"室内操作完成任务: {matched.title}",
            ))
        prev_level = profile.career_level
        result = await complete_task_internal(db, profile, matched, wallet)
        task_delta = 1
        xp_delta = result.get("xp_earned", 0)
        level_up = (profile.career_level or 0) > (prev_level or 0)
        _ = await check_achievements(db, profile.id, "task_complete")
        _ = await check_achievements(db, profile.id, "xp_gain")

    _record_metric(room.id, True, queue_wait=queue_wait)
    return InteractResult(
        success=True,
        reason="操作成功",
        task_delta=task_delta,
        xp_delta=xp_delta,
        level_up=level_up,
        cooldown_left_sec=action.cooldown_sec,
        queue_count=0,
        occupancy=_occupancy_for(room.id, action),
    )


@router.get("/interactions/metrics", summary="室内交互统计诊断")
async def interaction_metrics():
    return {
        "rooms": {str(room_id): _metric_out(room_id) for room_id in _INTERACTION_METRICS.keys()}
    }
