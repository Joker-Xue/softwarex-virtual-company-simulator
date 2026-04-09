"""
数据分析面板API
"""
from datetime import datetime, timedelta, UTC
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func, or_, and_

from app.database import get_db
from app.utils.security import get_current_active_user
from app.models.user import User
from app.models.agent_profile import AgentProfile
from app.models.agent_task import AgentTask
from app.models.agent_friendship import AgentFriendship
from app.models.agent_message import AgentMessage
from app.models.company_room import CompanyRoom
from app.schemas.agent_social import CAREER_LEVELS
from app.engine.analytics_engine import get_behavior_pattern, get_career_prediction

router = APIRouter()
FLOOR_Y_OFFSET = 700


def _decode_floor(pos_y: int | None) -> int:
    y = int(pos_y or 0)
    if y < 0:
        y = 0
    return y // FLOOR_Y_OFFSET + 1


def _decode_canvas_y(pos_y: int | None) -> int:
    y = int(pos_y or 0)
    if y < 0:
        y = 0
    return y % FLOOR_Y_OFFSET


async def _get_profile(user: User, db: AsyncSession) -> AgentProfile:
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")
    return profile


@router.get("/analytics/personal", summary="个人数据分析")
async def personal_analytics(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)

    # ── XP History: 从已完成任务聚合真实 XP ──
    today = datetime.now(UTC).date()
    total_xp = me.xp or 0
    thirty_days_ago = today - timedelta(days=29)

    from sqlalchemy import cast, Date
    xp_by_day_result = await db.execute(
        select(
            cast(AgentTask.completed_at, Date).label("day"),
            sa_func.sum(AgentTask.xp_reward).label("daily_xp"),
        )
        .where(
            AgentTask.assignee_id == me.id,
            AgentTask.status == "completed",
            AgentTask.completed_at >= datetime(thirty_days_ago.year, thirty_days_ago.month, thirty_days_ago.day, tzinfo=UTC),
        )
        .group_by(cast(AgentTask.completed_at, Date))
    )
    xp_map = {row.day: int(row.daily_xp) for row in xp_by_day_result}

    if xp_map:
        # 真实数据：累计方式构建历史
        cumulative = max(0, total_xp - sum(xp_map.values()))
        xp_history = []
        for i in range(30):
            day = today - timedelta(days=29 - i)
            cumulative += xp_map.get(day, 0)
            xp_history.append({"date": day.strftime("%m-%d"), "xp": min(cumulative, total_xp)})
    else:
        # 回退：新用户或无任务记录时，保留原有模拟公式
        xp_history = []
        for i in range(30):
            day = today - timedelta(days=29 - i)
            ratio = (i + 1) / 30
            cumulative = int(total_xp * sum(((k + 1) / 30) ** 1.5 for k in range(i + 1)) / sum((j / 30) ** 1.5 for j in range(1, 31))) if total_xp > 0 else 0
            xp_history.append({"date": day.strftime("%m-%d"), "xp": min(cumulative, total_xp)})
        if xp_history:
            xp_history[-1]["xp"] = total_xp

    # ── Task Stats ──
    completed_result = await db.execute(
        select(sa_func.count(AgentTask.id)).where(
            AgentTask.assignee_id == me.id,
            AgentTask.status == "completed",
        )
    )
    completed_count = completed_result.scalar() or 0

    in_progress_result = await db.execute(
        select(sa_func.count(AgentTask.id)).where(
            AgentTask.assignee_id == me.id,
            AgentTask.status == "in_progress",
        )
    )
    in_progress_count = in_progress_result.scalar() or 0

    total_result = await db.execute(
        select(sa_func.count(AgentTask.id)).where(
            AgentTask.assignee_id == me.id,
        )
    )
    total_count = total_result.scalar() or 0

    task_stats = {
        "completed": completed_count,
        "in_progress": in_progress_count,
        "total": total_count,
    }

    # ── Social Stats ──
    friends_result = await db.execute(
        select(sa_func.count(AgentFriendship.id)).where(
            or_(
                AgentFriendship.from_id == me.id,
                AgentFriendship.to_id == me.id,
            ),
            AgentFriendship.status == "accepted",
        )
    )
    friends_count = friends_result.scalar() or 0

    messages_sent_result = await db.execute(
        select(sa_func.count(AgentMessage.id)).where(
            AgentMessage.sender_id == me.id,
        )
    )
    messages_sent = messages_sent_result.scalar() or 0

    avg_affinity_result = await db.execute(
        select(sa_func.avg(AgentFriendship.affinity)).where(
            or_(
                AgentFriendship.from_id == me.id,
                AgentFriendship.to_id == me.id,
            ),
            AgentFriendship.status == "accepted",
        )
    )
    avg_affinity_raw = avg_affinity_result.scalar()
    avg_affinity = round(float(avg_affinity_raw), 1) if avg_affinity_raw is not None else 0

    social_stats = {
        "friends_count": friends_count,
        "messages_sent": messages_sent,
        "avg_affinity": avg_affinity,
    }

    # ── Top Friends (top 5 by affinity) ──
    # Friends where I am from_id
    top_from = await db.execute(
        select(
            AgentFriendship.affinity,
            AgentFriendship.to_id.label("friend_id"),
        ).where(
            AgentFriendship.from_id == me.id,
            AgentFriendship.status == "accepted",
        )
    )
    from_rows = top_from.all()

    # Friends where I am to_id
    top_to = await db.execute(
        select(
            AgentFriendship.affinity,
            AgentFriendship.from_id.label("friend_id"),
        ).where(
            AgentFriendship.to_id == me.id,
            AgentFriendship.status == "accepted",
        )
    )
    to_rows = top_to.all()

    all_friends = [(r.affinity or 50, r.friend_id) for r in from_rows] + \
                  [(r.affinity or 50, r.friend_id) for r in to_rows]
    all_friends.sort(key=lambda x: x[0], reverse=True)
    top5_ids = [fid for _, fid in all_friends[:5]]

    top_friends = []
    if top5_ids:
        profiles_result = await db.execute(
            select(AgentProfile).where(AgentProfile.id.in_(top5_ids))
        )
        profiles_map = {p.id: p for p in profiles_result.scalars().all()}
        for affinity_val, fid in all_friends[:5]:
            p = profiles_map.get(fid)
            if p:
                top_friends.append({
                    "nickname": p.nickname,
                    "affinity": affinity_val,
                    "avatar_key": p.avatar_key,
                })

    return {
        "xp_history": xp_history,
        "task_stats": task_stats,
        "social_stats": social_stats,
        "top_friends": top_friends,
    }


@router.get("/analytics/company", summary="公司数据分析")
async def company_analytics(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # Ensure user has a profile
    await _get_profile(user, db)

    # ── Department Stats ──
    dept_result = await db.execute(
        select(
            AgentProfile.department,
            sa_func.count(AgentProfile.id).label("count"),
            sa_func.avg(AgentProfile.xp).label("avg_xp"),
        ).group_by(AgentProfile.department)
    )
    department_stats = [
        {
            "department": row.department or "unassigned",
            "count": row.count,
            "avg_xp": round(float(row.avg_xp), 1) if row.avg_xp is not None else 0,
        }
        for row in dept_result.all()
    ]

    # ── Level Distribution ──
    level_result = await db.execute(
        select(
            AgentProfile.career_level,
            sa_func.count(AgentProfile.id).label("count"),
        ).group_by(AgentProfile.career_level)
        .order_by(AgentProfile.career_level)
    )
    level_distribution = [
        {
            "level": row.career_level,
            "title": CAREER_LEVELS.get(row.career_level, {}).get("title", "未知"),
            "count": row.count,
        }
        for row in level_result.all()
    ]

    # ── Top 10 Agents by XP ──
    top_result = await db.execute(
        select(AgentProfile)
        .order_by(AgentProfile.xp.desc())
        .limit(10)
    )
    top_agents = [
        {
            "nickname": agent.nickname,
            "xp": agent.xp,
            "career_level": agent.career_level,
            "department": agent.department or "unassigned",
        }
        for agent in top_result.scalars().all()
    ]

    # ── Active Rooms: count agents per room based on position ──
    rooms_result = await db.execute(select(CompanyRoom))
    rooms = rooms_result.scalars().all()

    agents_result = await db.execute(
        select(AgentProfile.pos_x, AgentProfile.pos_y).where(
            AgentProfile.is_online == True
        )
    )
    online_positions = agents_result.all()

    active_rooms = []
    for room in rooms:
        agent_count = 0
        for pos in online_positions:
            canvas_y = _decode_canvas_y(pos.pos_y)
            floor = _decode_floor(pos.pos_y)
            if (
                floor == (room.floor or 1)
                and room.x <= pos.pos_x <= room.x + room.width
                and room.y <= canvas_y <= room.y + room.height
            ):
                agent_count += 1
        active_rooms.append({
            "room_name": room.name,
            "room_type": room.room_type,
            "department": room.department,
            "capacity": room.capacity,
            "agent_count": agent_count,
        })

    # Sort by agent_count descending
    active_rooms.sort(key=lambda r: r["agent_count"], reverse=True)

    return {
        "department_stats": department_stats,
        "level_distribution": level_distribution,
        "top_agents": top_agents,
        "active_rooms": active_rooms,
    }


@router.get("/analytics/dashboard", summary="运营大屏实时数据")
async def dashboard_realtime(
    db: AsyncSession = Depends(get_db),
):
    """公司运营大屏API — 无需登录，供大屏展示使用"""
    from datetime import date

    today = date.today()
    now = datetime.now(UTC)

    # ── 在线人数 ──
    online_result = await db.execute(
        select(sa_func.count(AgentProfile.id)).where(AgentProfile.is_online == True)
    )
    online_count = online_result.scalar() or 0

    # ── 总员工数 ──
    total_agents_result = await db.execute(select(sa_func.count(AgentProfile.id)))
    total_agents = total_agents_result.scalar() or 0

    # ── 今日完成任务数 ──
    today_start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    today_tasks_result = await db.execute(
        select(sa_func.count(AgentTask.id)).where(
            AgentTask.status == "completed",
            AgentTask.completed_at >= today_start,
        )
    )
    today_tasks = today_tasks_result.scalar() or 0

    # ── 全公司总XP ──
    total_xp_result = await db.execute(
        select(sa_func.sum(AgentProfile.xp))
    )
    total_xp = total_xp_result.scalar() or 0

    # ── 部门产出趋势（最近7天，每天每部门完成任务数）──
    seven_days_ago = now - timedelta(days=7)
    from sqlalchemy import cast, Date
    dept_trend_result = await db.execute(
        select(
            AgentProfile.department,
            cast(AgentTask.completed_at, Date).label("day"),
            sa_func.count(AgentTask.id).label("count"),
        )
        .join(AgentProfile, AgentTask.assignee_id == AgentProfile.id)
        .where(
            AgentTask.status == "completed",
            AgentTask.completed_at >= seven_days_ago,
        )
        .group_by(AgentProfile.department, cast(AgentTask.completed_at, Date))
    )
    dept_trend_raw = dept_trend_result.all()
    dept_trend = {}
    for row in dept_trend_raw:
        dept = row.department or "unassigned"
        if dept not in dept_trend:
            dept_trend[dept] = {}
        dept_trend[dept][row.day.strftime("%m-%d") if row.day else ""] = row.count

    # ── 职级分布 ──
    level_result = await db.execute(
        select(
            AgentProfile.career_level,
            sa_func.count(AgentProfile.id).label("count"),
        ).group_by(AgentProfile.career_level)
        .order_by(AgentProfile.career_level)
    )
    level_distribution = [
        {
            "level": row.career_level,
            "title": CAREER_LEVELS.get(row.career_level, {}).get("title", "未知"),
            "count": row.count,
        }
        for row in level_result.all()
    ]

    # ── Top 10 排行榜 ──
    top_result = await db.execute(
        select(AgentProfile).order_by(AgentProfile.xp.desc()).limit(10)
    )
    top_agents = [
        {
            "rank": i + 1,
            "nickname": a.nickname,
            "xp": a.xp,
            "career_level": a.career_level,
            "career_title": CAREER_LEVELS.get(a.career_level, {}).get("title", "未知"),
            "department": a.department or "unassigned",
            "avatar_key": a.avatar_key,
        }
        for i, a in enumerate(top_result.scalars().all())
    ]

    # ── 部门统计 ──
    dept_result = await db.execute(
        select(
            AgentProfile.department,
            sa_func.count(AgentProfile.id).label("count"),
            sa_func.avg(AgentProfile.xp).label("avg_xp"),
            sa_func.sum(AgentProfile.tasks_completed).label("total_tasks"),
        ).group_by(AgentProfile.department)
    )
    department_stats = [
        {
            "department": row.department or "unassigned",
            "count": row.count,
            "avg_xp": round(float(row.avg_xp), 1) if row.avg_xp else 0,
            "total_tasks": row.total_tasks or 0,
        }
        for row in dept_result.all()
    ]

    # ── 在线Agent位置（供地图展示）──
    online_agents_result = await db.execute(
        select(
            AgentProfile.id,
            AgentProfile.nickname,
            AgentProfile.pos_x,
            AgentProfile.pos_y,
            AgentProfile.current_action,
            AgentProfile.department,
            AgentProfile.avatar_key,
        ).where(AgentProfile.is_online == True)
    )
    online_agents = [
        {
            "id": a.id,
            "nickname": a.nickname,
            "x": a.pos_x,
            "y": a.pos_y,
            "canvas_y": _decode_canvas_y(a.pos_y),
            "floor": _decode_floor(a.pos_y),
            "action": a.current_action,
            "department": a.department,
            "avatar_key": a.avatar_key,
        }
        for a in online_agents_result.all()
    ]

    # ── 活跃房间 ──
    rooms_result = await db.execute(select(CompanyRoom))
    rooms = rooms_result.scalars().all()
    active_rooms = []
    for room in rooms:
        count = sum(
            1 for a in online_agents
            if room.x <= a["x"] <= room.x + room.width
            and room.y <= a["canvas_y"] <= room.y + room.height
            and a["floor"] == (room.floor or 1)
        )
        active_rooms.append({
            "name": room.name,
            "type": room.room_type,
            "floor": room.floor,
            "agent_count": count,
            "capacity": room.capacity,
        })

    return {
        "kpi": {
            "online_count": online_count,
            "total_agents": total_agents,
            "today_tasks": today_tasks,
            "total_xp": int(total_xp),
        },
        "dept_trend": dept_trend,
        "level_distribution": level_distribution,
        "top_agents": top_agents,
        "department_stats": department_stats,
        "online_agents": online_agents,
        "active_rooms": active_rooms,
    }


@router.get("/analytics/behavior", summary="行为模式分析")
async def behavior_analysis(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """分析Agent近30天行为模式：活跃时段热力图、行为偏好分布、个性化建议、MBTI对比"""
    me = await _get_profile(user, db)
    return await get_behavior_pattern(db, me.id)


@router.get("/analytics/prediction", summary="职业轨迹预测")
async def career_prediction(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """基于当前数据预测晋升时间和职业发展路径"""
    me = await _get_profile(user, db)
    return await get_career_prediction(db, me.id)
