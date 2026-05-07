"""
WebSocketendpoint - Real-time world synchronization
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.utils.security import decode_access_token
from app.utils.sanitize import sanitize_text
from app.models.agent_profile import AgentProfile
from app.models.agent_message import AgentMessage
from app.routers.agent_world import SEED_ROOMS
from app.engine.named_spots import snap_to_nearest_spot, get_spot_pos, get_spot_name_by_pos

logger = logging.getLogger(__name__)
router = APIRouter()

FLOOR_Y_OFFSET = 700
MAX_FLOOR = 3
MAX_CANVAS_X = 600
MAX_CANVAS_Y = 699
MAX_ENCODED_Y = FLOOR_Y_OFFSET * MAX_FLOOR - 1


def _decode_floor_from_pos_y(pos_y: int) -> int:
    """Decode floor from encoded pos_y using shared floor-offset convention."""
    floor = pos_y // FLOOR_Y_OFFSET + 1
    return max(1, min(MAX_FLOOR, floor))


def _decode_canvas_y(pos_y: int) -> int:
    """Decode canvas y (0..699) from encoded pos_y."""
    return pos_y % FLOOR_Y_OFFSET


def _detect_floor(x: int, encoded_y: int) -> int:
    """
    Detect the room floor based on coded coordinates。
    First press pos_y floor offset to decode floor，Then hit the room according to the canvas coordinates within the floor.
    """
    floor = _decode_floor_from_pos_y(encoded_y)
    canvas_y = _decode_canvas_y(encoded_y)
    for room in SEED_ROOMS:
        if room.get("floor", 1) != floor:
            continue
        rx, ry = room["x"], room["y"]
        rw, rh = room["width"], room["height"]
        if rx <= x <= rx + rw and ry <= canvas_y <= ry + rh:
            return room["floor"]
    return floor


class ConnectionManager:
    """WebSocket connection manager - supports floor AOIfilter + heartbeat timeout Detection"""

    HEARTBEAT_TIMEOUT = 60  # No activity for more than 60 seconds is considered a dead connection
    CLEANUP_INTERVAL = 30   # Scan every 30 seconds

    def __init__(self):
        # agent_id -> WebSocket
        self.active: Dict[int, WebSocket] = {}
        # agent_id -> floor (Floor AOI tracking)
        self.floor_map: Dict[int, int] = {}
        # agent_id -> last activity timestamp
        self._last_activity: Dict[int, float] = {}
        # Background cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None

    def _ensure_cleanup_task(self):
        """Make sure the background cleanup coroutine is started"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        """Clean up dead connections regularly"""
        while True:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                await self.cleanup_dead_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("WS cleanup error: %s", e)

    async def cleanup_dead_connections(self):
        """Remove connections that have been inactive for more than HEARTBEAT_TIMEOUT seconds"""
        now = time.time()
        dead = [
            agent_id for agent_id, last in self._last_activity.items()
            if now - last > self.HEARTBEAT_TIMEOUT
        ]
        for agent_id in dead:
            logger.info("Cleaning up dead WS connection: agent=%s", agent_id)
            ws = self.active.get(agent_id)
            if ws:
                try:
                    await ws.close(code=4003, reason="Heartbeat timeout")
                except Exception:
                    pass
            self.disconnect(agent_id)

    def touch(self, agent_id: int):
        """Update last Activitytime"""
        self._last_activity[agent_id] = time.time()

    async def connect(self, agent_id: int, ws: WebSocket, floor: int = 1, accept: bool = True):
        if accept:
            await ws.accept()
        self.active[agent_id] = ws
        self.floor_map[agent_id] = floor
        self._last_activity[agent_id] = time.time()
        self._ensure_cleanup_task()

    def disconnect(self, agent_id: int):
        self.active.pop(agent_id, None)
        self.floor_map.pop(agent_id, None)
        self._last_activity.pop(agent_id, None)

    def update_floor(self, agent_id: int, floor: int):
        """Update the floor where the agent is located"""
        self.floor_map[agent_id] = floor

    async def send_to(self, agent_id: int, data: dict):
        ws = self.active.get(agent_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(agent_id)

    async def broadcast(self, data: dict, exclude: int = None):
        """overall situation - Used for global events such as join/leave/chat"""
        dead = []
        for aid, ws in self.active.items():
            if aid == exclude:
                continue
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(aid)
        for aid in dead:
            self.active.pop(aid, None)
            self.floor_map.pop(aid, None)

    async def broadcast_floor(self, floor: int, data: dict, exclude: int = None):
        """Floor Broadcast - Send only to agents on the same floor（AOIfilter）"""
        dead = []
        for aid, ws in self.active.items():
            if aid == exclude:
                continue
            if self.floor_map.get(aid) != floor:
                continue
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(aid)
        for aid in dead:
            self.active.pop(aid, None)
            self.floor_map.pop(aid, None)


manager = ConnectionManager()


async def _auth_ws(token: str) -> int | None:
    """Parse user_id from token"""
    payload = decode_access_token(token)
    if not payload:
        return None
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        return None


@router.websocket("/world")
async def ws_world(ws: WebSocket):
    """WebSocket endpoint：Read token authentication from the first msgsinformation（Not passing URL query param）"""
    await ws.accept()

    # Waiting for the first msgsinformation to carry token
    try:
        raw = await ws.receive_text()
        first_msg = json.loads(raw)
        token = first_msg.get("token", "")
    except Exception:
        await ws.close(code=4001, reason="Authentication failed：the first message must include a token")
        return

    user_id = await _auth_ws(token)
    if not user_id:
        await ws.close(code=4001, reason="Authentication failed")
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            await ws.close(code=4002, reason="Profile has not been created yet")
            return

        # compatible old data：If the Current position is not a semantic point，Automatically snap to the nearest legal point when connecting
        if get_spot_name_by_pos(profile.pos_x, profile.pos_y) is None:
            snapped_spot = snap_to_nearest_spot(
                x=profile.pos_x or 0,
                encoded_y=profile.pos_y or 0,
                career_level=profile.career_level or 0,
                department=profile.department or "",
                career_path=profile.career_path or "",
            )
            snapped_x, snapped_y = get_spot_pos(snapped_spot)
            profile.pos_x = snapped_x
            profile.pos_y = snapped_y

        agent_id = profile.id
        profile.is_online = True
        profile.last_seen = datetime.now(timezone.utc)
        await db.commit()

    # Detection initial floor
    initial_floor = _detect_floor(profile.pos_x, profile.pos_y)
    await manager.connect(agent_id, ws, floor=initial_floor, accept=False)

    # Broadcasting online（overall situation is visible）
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.id == agent_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            await manager.broadcast({
                "type": "agent_join",
                "agent": {
                    "id": profile.id,
                    "nickname": profile.nickname,
                    "avatar_key": profile.avatar_key,
                    "pos_x": profile.pos_x,
                    "pos_y": profile.pos_y,
                    "current_action": profile.current_action,
                    "career_level": profile.career_level,
                    "department": profile.department,
                },
            }, exclude=agent_id)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                manager.touch(agent_id)
                await ws.send_json({"type": "pong"})

            elif msg_type == "move":
                manager.touch(agent_id)
                x = int(data.get("x", 0))
                y = int(data.get("y", 0))
                x = max(0, min(MAX_CANVAS_X, x))
                y = max(0, min(MAX_ENCODED_Y, y))
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(AgentProfile).where(AgentProfile.id == agent_id)
                    )
                    p = result.scalar_one_or_none()
                    if p:
                        snapped_spot = snap_to_nearest_spot(
                            x=x,
                            encoded_y=y,
                            career_level=p.career_level or 0,
                            department=p.department or "",
                            career_path=p.career_path or "",
                        )
                        snapped_x, snapped_y = get_spot_pos(snapped_spot)
                        p.pos_x = snapped_x
                        p.pos_y = snapped_y
                        p.current_action = "moving"
                        await db.commit()
                        x, y = snapped_x, snapped_y
                # DetectionNew Floor，Update AOI
                new_floor = _detect_floor(x, y)
                old_floor = manager.floor_map.get(agent_id, 1)
                if new_floor != old_floor:
                    # Notify old floor：agent leaves view
                    await manager.broadcast_floor(
                        old_floor,
                        {"type": "agent_floor_leave", "agent_id": agent_id, "floor": new_floor},
                        exclude=agent_id,
                    )
                    manager.update_floor(agent_id, new_floor)
                    # Notify new floor：agent comes into view
                    await manager.broadcast_floor(
                        new_floor,
                        {"type": "agent_floor_join", "agent_id": agent_id, "x": x, "y": y, "floor": new_floor},
                        exclude=agent_id,
                    )
                # Only broadcast to agents on the same floor（AOIfilter）
                await manager.broadcast_floor(
                    new_floor,
                    {"type": "agent_move", "agent_id": agent_id, "x": x, "y": y},
                    exclude=agent_id,
                )

            elif msg_type == "action":
                action = str(data.get("action", "idle"))[:50]
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(AgentProfile).where(AgentProfile.id == agent_id)
                    )
                    p = result.scalar_one_or_none()
                    if p:
                        p.current_action = action
                        await db.commit()
                # actionEvents are only broadcast to agents on the same floor（AOIfilter）
                agent_floor = manager.floor_map.get(agent_id, 1)
                await manager.broadcast_floor(
                    agent_floor,
                    {"type": "agent_action", "agent_id": agent_id, "action": action},
                    exclude=agent_id,
                )

            elif msg_type == "chat":
                manager.touch(agent_id)
                to_id = data.get("to")
                content = sanitize_text(str(data.get("content", ""))[:2000])
                if to_id and content:
                    async with AsyncSessionLocal() as db:
                        msg = AgentMessage(
                            sender_id=agent_id,
                            receiver_id=int(to_id),
                            content=content,
                        )
                        db.add(msg)
                        await db.commit()
                    await manager.send_to(int(to_id), {
                        "type": "new_message",
                        "from": agent_id,
                        "content": content,
                    })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WS error agent=%s: %s", agent_id, e)
    finally:
        manager.disconnect(agent_id)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AgentProfile).where(AgentProfile.id == agent_id)
            )
            p = result.scalar_one_or_none()
            if p:
                p.is_online = False
                p.last_seen = datetime.now(timezone.utc)
                await db.commit()
        await manager.broadcast(
            {"type": "agent_leave", "agent_id": agent_id}
        )
