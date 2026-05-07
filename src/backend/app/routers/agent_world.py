"""
Maps and World API
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
                    name=str(obj.get("name", f"property{idx+1}")),
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
            name="center of room",
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

# Seed room data  multi-floor layout
# each floor 600x600 canvas，3rooms arranged horizontally
# Room 1: x=0,   y=100, w=180, h=400
# Room 2: x=210, y=100, w=180, h=400
# Room 3: x=420, y=100, w=180, h=400
# interior_objects Coordinates are relative to the interior of the room (0,0)-(180,400)
SEED_ROOMS = [
    # ── 1F Lobby Floor ──
    {
        "name": "Lobby", "room_type": "lounge", "department": "general",
        "x": 0, "y": 100, "width": 180, "height": 400, "capacity": 30,
        "floor": 1, "description": "Company Central Lobby",
        "interior_objects": [
            {"type": "desk", "name": "front desk reception desk", "x": 40, "y": 20, "width": 100, "height": 30, "interactive": True},
            {"type": "sofa", "name": "Sofa A", "x": 10, "y": 100, "width": 60, "height": 30, "interactive": False},
            {"type": "sofa", "name": "Sofa B", "x": 110, "y": 100, "width": 60, "height": 30, "interactive": False},
            {"type": "table", "name": "coffee table", "x": 60, "y": 140, "width": 60, "height": 25, "interactive": False},
            {"type": "water_fountain", "name": "fountain", "x": 65, "y": 220, "width": 50, "height": 50, "interactive": True},
            {"type": "info_board", "name": "InfoAnnouncement column", "x": 10, "y": 310, "width": 60, "height": 50, "interactive": True},
            {"type": "plant", "name": "Green plant A", "x": 10, "y": 70, "width": 20, "height": 20, "interactive": False},
            {"type": "plant", "name": "Green plant B", "x": 150, "y": 70, "width": 20, "height": 20, "interactive": False},
        ],
    },
    {
        "name": "Cafe", "room_type": "cafeteria", "department": "general",
        "x": 210, "y": 100, "width": 180, "height": 400, "capacity": 25,
        "floor": 1, "description": "Rest and Social area",
        "interior_objects": [
            {"type": "table", "name": "Dining table 1", "x": 15, "y": 30, "width": 50, "height": 35, "interactive": False},
            {"type": "table", "name": "Dining table 2", "x": 110, "y": 30, "width": 50, "height": 35, "interactive": False},
            {"type": "table", "name": "Dining table 3", "x": 15, "y": 120, "width": 50, "height": 35, "interactive": False},
            {"type": "table", "name": "dining table 4", "x": 110, "y": 120, "width": 50, "height": 35, "interactive": False},
            {"type": "coffee_machine", "name": "coffee machine", "x": 130, "y": 220, "width": 35, "height": 30, "interactive": True},
            {"type": "vending_machine", "name": "vending machine", "x": 130, "y": 270, "width": 35, "height": 45, "interactive": True},
            {"type": "bar_counter", "name": "Bar counter", "x": 20, "y": 230, "width": 90, "height": 25, "interactive": True},
            {"type": "plant", "name": "Green plant A", "x": 10, "y": 340, "width": 20, "height": 20, "interactive": False},
            {"type": "plant", "name": "Green plant B", "x": 80, "y": 340, "width": 20, "height": 20, "interactive": False},
        ],
    },
    {
        "name": "HR Department", "room_type": "office", "department": "hr",
        "x": 420, "y": 100, "width": 180, "height": 400, "capacity": 15,
        "floor": 1, "description": "HR TeamOffice",
        "interior_objects": [
            {"type": "desk", "name": "desk1", "x": 15, "y": 40, "width": 60, "height": 30, "interactive": True},
            {"type": "desk", "name": "desk2", "x": 15, "y": 100, "width": 60, "height": 30, "interactive": True},
            {"type": "desk", "name": "desk3", "x": 105, "y": 40, "width": 60, "height": 30, "interactive": True},
            {"type": "interview_booth", "name": "Interview room", "x": 95, "y": 140, "width": 70, "height": 60, "interactive": True},
            {"type": "filing_cabinet", "name": "Filing cabinet A", "x": 10, "y": 240, "width": 30, "height": 55, "interactive": True},
            {"type": "filing_cabinet", "name": "Filing cabinet B", "x": 55, "y": 240, "width": 30, "height": 55, "interactive": True},
            {"type": "notice_board", "name": "Announcement column", "x": 60, "y": 10, "width": 60, "height": 20, "interactive": True},
        ],
    },
    # ── 2F Office Floor ──
    # left column(full height): Engineering  | Middle column: Marketing(superior)/Product(Down) | Right column: Finance(superior)/Operations(Down)
    {
        "name": "Engineering", "room_type": "office", "department": "engineering",
        "x": 0, "y": 50, "width": 200, "height": 450, "capacity": 20,
        "floor": 2, "description": "Engineering technology teamOffice",
        "interior_objects": [
            {"type": "desk", "name": "desk1", "x": 10, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "computer", "name": "Computer 1", "x": 20, "y": 43, "width": 18, "height": 14, "interactive": True},
            {"type": "desk", "name": "desk2", "x": 10, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "computer", "name": "Computer 2", "x": 20, "y": 93, "width": 18, "height": 14, "interactive": True},
            {"type": "desk", "name": "desk3", "x": 10, "y": 140, "width": 60, "height": 28, "interactive": True},
            {"type": "computer", "name": "Computer 3", "x": 20, "y": 143, "width": 18, "height": 14, "interactive": True},
            {"type": "desk", "name": "desk4", "x": 120, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "computer", "name": "Computer 4", "x": 130, "y": 43, "width": 18, "height": 14, "interactive": True},
            {"type": "desk", "name": "desk5", "x": 120, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "computer", "name": "computer 5", "x": 130, "y": 93, "width": 18, "height": 14, "interactive": True},
            {"type": "desk", "name": "desk6", "x": 120, "y": 140, "width": 60, "height": 28, "interactive": True},
            {"type": "computer", "name": "Computer 6", "x": 130, "y": 143, "width": 18, "height": 14, "interactive": True},
            {"type": "server_rack", "name": "server rack", "x": 75, "y": 260, "width": 50, "height": 60, "interactive": True},
            {"type": "whiteboard", "name": "whiteboard", "x": 65, "y": 10, "width": 70, "height": 20, "interactive": True},
        ],
    },
    {
        "name": "Marketing", "room_type": "office", "department": "marketing",
        "x": 220, "y": 50, "width": 180, "height": 210, "capacity": 12,
        "floor": 2, "description": "Marketing TeamOffice",
        "interior_objects": [
            {"type": "desk", "name": "desk1", "x": 10, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "desk2", "x": 10, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "desk3", "x": 110, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "desk4", "x": 110, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "presentation_screen", "name": "Demo screen", "x": 50, "y": 10, "width": 80, "height": 20, "interactive": True},
            {"type": "mood_board", "name": "inspiration board", "x": 120, "y": 140, "width": 50, "height": 50, "interactive": True},
        ],
    },
    {
        "name": "Product", "room_type": "office", "department": "product",
        "x": 220, "y": 280, "width": 180, "height": 220, "capacity": 12,
        "floor": 2, "description": "Product management team Office",
        "interior_objects": [
            {"type": "desk", "name": "desk1", "x": 10, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "desk2", "x": 10, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "desk3", "x": 110, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "desk4", "x": 110, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "whiteboard", "name": "Product whiteboard", "x": 50, "y": 10, "width": 80, "height": 20, "interactive": True},
            {"type": "presentation_screen", "name": "Prototype display screen", "x": 10, "y": 150, "width": 70, "height": 50, "interactive": True},
        ],
    },
    {
        "name": "Finance", "room_type": "office", "department": "finance",
        "x": 420, "y": 50, "width": 180, "height": 210, "capacity": 10,
        "floor": 2, "description": "Finance management team Office",
        "interior_objects": [
            {"type": "desk", "name": "desk1", "x": 10, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "desk2", "x": 10, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "desk3", "x": 110, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "desk4", "x": 110, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "safe", "name": "safe", "x": 70, "y": 140, "width": 40, "height": 40, "interactive": True},
            {"type": "calculator_station", "name": "Accounting desk", "x": 50, "y": 10, "width": 80, "height": 20, "interactive": True},
        ],
    },
    {
        "name": "Operations", "room_type": "office", "department": "operations",
        "x": 420, "y": 280, "width": 180, "height": 220, "capacity": 12,
        "floor": 2, "description": "Operations Growth TeamOffice",
        "interior_objects": [
            {"type": "desk", "name": "desk1", "x": 10, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "desk2", "x": 10, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "desk3", "x": 110, "y": 40, "width": 60, "height": 28, "interactive": True},
            {"type": "desk", "name": "desk4", "x": 110, "y": 90, "width": 60, "height": 28, "interactive": True},
            {"type": "presentation_screen", "name": "data big screen", "x": 50, "y": 10, "width": 80, "height": 20, "interactive": True},
            {"type": "mood_board", "name": "Operations Kanban", "x": 10, "y": 150, "width": 60, "height": 50, "interactive": True},
        ],
    },
    # ── 3F Management Floor ──
    {
        "name": "Meeting Room", "room_type": "meeting", "department": "general",
        "x": 0, "y": 100, "width": 180, "height": 400, "capacity": 12,
        "floor": 3, "description": "Large Meeting Room",
        "interior_objects": [
            {"type": "table", "name": "Meeting table", "x": 30, "y": 100, "width": 120, "height": 60, "interactive": False},
            {"type": "chair", "name": "meeting chair1", "x": 40, "y": 80, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "meeting chair2", "x": 70, "y": 80, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "meeting chair3", "x": 100, "y": 80, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "meeting chair4", "x": 130, "y": 80, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "meeting chair5", "x": 40, "y": 165, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "meeting chair6", "x": 70, "y": 165, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "meeting chair7", "x": 100, "y": 165, "width": 18, "height": 18, "interactive": False},
            {"type": "chair", "name": "meeting chair8", "x": 130, "y": 165, "width": 18, "height": 18, "interactive": False},
            {"type": "projector_screen", "name": "projection screen", "x": 10, "y": 20, "width": 160, "height": 40, "interactive": True},
            {"type": "whiteboard", "name": "whiteboard", "x": 30, "y": 260, "width": 120, "height": 50, "interactive": True},
        ],
    },
    {
        "name": "Director Office", "room_type": "office", "department": "management",
        "x": 210, "y": 100, "width": 180, "height": 400, "capacity": 4,
        "floor": 3, "description": "Director level Office",
        "interior_objects": [
            {"type": "desk", "name": "Director's desk", "x": 50, "y": 80, "width": 80, "height": 35, "interactive": True},
            {"type": "chair", "name": "Office chair A", "x": 65, "y": 125, "width": 22, "height": 22, "interactive": False},
            {"type": "chair", "name": "Office chair B", "x": 100, "y": 125, "width": 22, "height": 22, "interactive": False},
            {"type": "filing_cabinet", "name": "filing cabinet", "x": 10, "y": 20, "width": 30, "height": 55, "interactive": True},
            {"type": "whiteboard", "name": "whiteboard", "x": 130, "y": 20, "width": 40, "height": 60, "interactive": True},
        ],
    },
    {
        "name": "CEO Office", "room_type": "ceo_office", "department": "management",
        "x": 420, "y": 100, "width": 180, "height": 400, "capacity": 2,
        "floor": 3, "description": "The office of the company's top decision-maker",
        "interior_objects": [
            {"type": "desk", "name": "executive desk", "x": 50, "y": 80, "width": 80, "height": 35, "interactive": True},
            {"type": "chair", "name": "Leather seats", "x": 75, "y": 125, "width": 25, "height": 25, "interactive": False},
            {"type": "bookshelf", "name": "bookshelf", "x": 10, "y": 15, "width": 30, "height": 90, "interactive": True},
            {"type": "plant", "name": "green plants", "x": 145, "y": 15, "width": 25, "height": 25, "interactive": False},
            {"type": "globe", "name": "globe", "x": 140, "y": 130, "width": 25, "height": 25, "interactive": True},
        ],
    },
]

ROOM_NAME_ALIASES = {
    "Meeting Room": ["Meeting RoomA"],
}


def _fill_career_title(profile: AgentProfile) -> dict:
    data = {c.name: getattr(profile, c.name) for c in AgentProfile.__table__.columns}
    data["career_title"] = CAREER_LEVELS.get(profile.career_level, {}).get("title", "Unknown")
    # personality may be dict（NPCmark）or list，uniformly converted to list
    p = data.get("personality")
    if isinstance(p, dict):
        data["personality"] = list(p.get("tags", []))  # NPC: Get tags or an empty list
    elif not isinstance(p, list):
        data["personality"] = []
    # daily_schedule: Filter out the internals of the simulation engine msgs eyes（_sim_state, _decision_log）
    schedule = data.get("daily_schedule") or []
    if isinstance(schedule, list):
        data["daily_schedule"] = [
            s for s in schedule
            if isinstance(s, dict) and not s.get("_sim_state") and "_decision_log" not in s
        ]
    return data


def _is_npc_profile(profile: AgentProfile) -> bool:
    """compatible personality historical structure，Identify NPC Role。"""
    p = profile.personality
    if isinstance(p, dict):
        return bool(p.get("is_npc"))
    if isinstance(p, list):
        for item in p:
            if isinstance(item, dict) and item.get("is_npc"):
                return True
    return False


async def _ensure_all_rooms(db: AsyncSession):
    """Upsert-lite: Make sure all rooms in SEED_ROOMS exist in DB（Add if missing，NULL fields are patched）。
    match by name，Fix rows where floor/interior_objects is NULL in old DB，avoid duplicate insertion。"""
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
        # Clear room center cache，Ensure that the repaired room is included in the next simulation decision-making
        from app.engine.agent_ai import clear_room_cache
        clear_room_cache()
    return changed


@router.get("/map", response_model=list[CompanyRoomOut], summary="Get Company Map")
async def get_map(
    floor: Optional[int] = Query(None, description="Floor filter，If not passed, Back to all floors"),
    db: AsyncSession = Depends(get_db),
):
    # Make sure all rooms exist（Idempotent，Fully created new environment，The old environment supplements the missing rooms）
    await _ensure_all_rooms(db)
    stmt = select(CompanyRoom)
    if floor is not None:
        stmt = stmt.where(CompanyRoom.floor == floor)
    result = await db.execute(stmt)
    rooms = result.scalars().all()
    return rooms


@router.get("/agents/online", response_model=list[AgentProfileOut], summary="Get Online Agents")
async def get_online_agents(db: AsyncSession = Depends(get_db)):
    # “VisibleRole”Strategy：
    # 1) All online real people/players
    # 2) All NPCs（anchoredworld，Avoid being affected by is_online dirty state, causing the floor to be blank）
    result = await db.execute(select(AgentProfile))
    all_agents = result.scalars().all()
    agents = [
        a for a in all_agents
        if a.is_online or _is_npc_profile(a)
    ]
    return [AgentProfileOut(**_fill_career_title(a)) for a in agents]


@router.post("/move", response_model=AgentProfileOut, summary="Move Role")
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
        raise HTTPException(404, "Profile has not been created yet")

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
        raise HTTPException(404, "Profile has not been created yet")
    room = (await db.execute(select(CompanyRoom).where(CompanyRoom.id == room_id))).scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Room does not exist")
    return profile, room


@router.get("/rooms/{room_id}/interactions", response_model=RoomInteractionsOut, summary="Get the interactive structure of the room")
async def get_room_interactions(
    room_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    _ = user
    room = (await db.execute(select(CompanyRoom).where(CompanyRoom.id == room_id))).scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Room does not exist")
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


@router.post("/rooms/{room_id}/move-inside", response_model=MoveInsideOut, summary="Move indoors to legal interaction point")
async def move_inside_room(
    room_id: int,
    body: MoveInsideRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    profile, room = await _get_user_profile_room(db, user, room_id)
    spots = _build_interaction_spots(room)
    if not spots:
        raise HTTPException(400, "There are no movable points in this room")
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


@router.post("/rooms/{room_id}/interact", response_model=InteractResult, summary="Execute room object interaction and link Task")
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
        raise HTTPException(400, "Invalid or non-interactive object")

    floor = room.floor or 1
    profile_canvas_y = profile.pos_y % 700
    if not (
        room.x <= profile.pos_x <= room.x + room.width
        and room.y <= profile_canvas_y <= room.y + room.height
        and (profile.pos_y // 700 + 1) == floor
    ):
        _record_metric(room.id, False, "not_in_room")
        return InteractResult(success=False, reason="Please enter the room first before proceeding.", queue_count=0)

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
            reason="Object occupied，Queued",
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
    # If no tasks exist, generate daily tasks once to keep loop closed loop available。
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
                description=f"Indoor operation Complete Task: {matched.title}",
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
        reason="Operation successful",
        task_delta=task_delta,
        xp_delta=xp_delta,
        level_up=level_up,
        cooldown_left_sec=action.cooldown_sec,
        queue_count=0,
        occupancy=_occupancy_for(room.id, action),
    )


@router.get("/interactions/metrics", summary="Indoor interactive statistical diagnosis")
async def interaction_metrics():
    return {
        "rooms": {str(room_id): _metric_out(room_id) for room_id in _INTERACTION_METRICS.keys()}
    }
