"""
社交活动API
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func

from app.database import get_db
from app.utils.security import get_current_active_user
from app.models.user import User
from app.models.agent_profile import AgentProfile
from app.models.company_event import CompanyEvent
from app.models.coin_wallet import CoinWallet, CoinTransaction

router = APIRouter()


async def _get_profile(user: User, db: AsyncSession) -> AgentProfile:
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")
    return profile


@router.get("/list", summary="获取活动列表")
async def list_events(
    status: str = Query(None, description="upcoming/active/ended"),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_profile(user, db)

    query = select(CompanyEvent).order_by(CompanyEvent.scheduled_at.asc())
    if status:
        query = query.where(CompanyEvent.is_active == status)

    result = await db.execute(query)
    events = result.scalars().all()

    # 批量查询房间名称
    room_ids = [e.room_id for e in events if e.room_id]
    room_names: dict[int, str] = {}
    if room_ids:
        from app.models.company_room import CompanyRoom
        room_res = await db.execute(
            select(CompanyRoom.id, CompanyRoom.name).where(CompanyRoom.id.in_(room_ids))
        )
        room_names = {row.id: row.name for row in room_res.all()}

    return [
        {
            "id": e.id,
            "name": e.name,
            "event_type": e.event_type,
            "description": e.description,
            "room_id": e.room_id,
            "room_name": room_names.get(e.room_id) if e.room_id else None,
            "scheduled_at": e.scheduled_at.isoformat() if e.scheduled_at else None,
            "duration_minutes": e.duration_minutes,
            "max_participants": e.max_participants,
            "participants": e.participants or [],
            "participant_count": len(e.participants or []),
            "rewards_xp": e.rewards_xp,
            "rewards_coins": e.rewards_coins,
            "is_active": e.is_active,
        }
        for e in events
    ]


@router.get("/{event_id}", summary="活动详情")
async def get_event(
    event_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_profile(user, db)

    result = await db.execute(
        select(CompanyEvent).where(CompanyEvent.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "活动不存在")

    # 获取参与者详情
    participants_info = []
    participant_ids = event.participants or []
    if participant_ids:
        pr = await db.execute(
            select(AgentProfile).where(AgentProfile.id.in_(participant_ids))
        )
        for p in pr.scalars().all():
            participants_info.append({
                "id": p.id,
                "nickname": p.nickname,
                "avatar_key": p.avatar_key,
                "department": p.department,
            })

    return {
        "id": event.id,
        "name": event.name,
        "event_type": event.event_type,
        "description": event.description,
        "room_id": event.room_id,
        "scheduled_at": event.scheduled_at.isoformat() if event.scheduled_at else None,
        "duration_minutes": event.duration_minutes,
        "max_participants": event.max_participants,
        "participants": participants_info,
        "participant_count": len(participant_ids),
        "rewards_xp": event.rewards_xp,
        "rewards_coins": event.rewards_coins,
        "is_active": event.is_active,
    }


@router.post("/{event_id}/join", summary="参加活动")
async def join_event(
    event_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    me = await _get_profile(user, db)

    result = await db.execute(
        select(CompanyEvent).where(CompanyEvent.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "活动不存在")

    if event.is_active == "ended":
        raise HTTPException(400, "活动已结束")

    participants = list(event.participants or [])
    if me.id in participants:
        raise HTTPException(409, "已参加此活动")

    if len(participants) >= event.max_participants:
        raise HTTPException(400, "活动人数已满")

    participants.append(me.id)
    event.participants = participants
    await db.flush()

    # 发放奖励
    rewards_given = False
    if event.rewards_xp > 0:
        me.xp = (me.xp or 0) + event.rewards_xp
        rewards_given = True

    if event.rewards_coins > 0:
        wallet_result = await db.execute(
            select(CoinWallet).where(CoinWallet.user_id == user.id)
        )
        wallet = wallet_result.scalar_one_or_none()
        if wallet:
            wallet.balance += event.rewards_coins
            tx = CoinTransaction(
                user_id=user.id,
                amount=event.rewards_coins,
                tx_type="event_reward",
                description=f"参加活动「{event.name}」奖励",
            )
            db.add(tx)
            rewards_given = True

    await db.flush()

    return {
        "message": f"成功参加活动「{event.name}」",
        "participant_count": len(participants),
        "rewards": {
            "xp": event.rewards_xp,
            "coins": event.rewards_coins,
        } if rewards_given else None,
    }


@router.post("/generate-weekly", summary="生成本周活动")
async def generate_weekly_events(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """管理接口：生成本周的预设活动"""
    await _get_profile(user, db)

    now = datetime.now(timezone.utc)
    # 本周五
    days_until_friday = (4 - now.weekday()) % 7
    if days_until_friday == 0 and now.hour >= 18:
        days_until_friday = 7
    friday = now + timedelta(days=days_until_friday)

    # 获取咖啡厅房间ID
    room_result = await db.execute(
        select(CompanyRoom.id).where(CompanyRoom.room_type == "cafeteria").limit(1)
    )
    cafe_room_id = None
    row = room_result.first()
    if row:
        cafe_room_id = row[0]

    templates = [
        {
            "name": "周五下午茶",
            "event_type": "tea_break",
            "description": "每周五的下午茶时光，放松身心，和同事聊聊天！",
            "scheduled_at": friday.replace(hour=15, minute=0, second=0, microsecond=0),
            "duration_minutes": 60,
            "max_participants": 30,
            "rewards_xp": 15,
            "rewards_coins": 8,
            "room_id": cafe_room_id,
        },
        {
            "name": "团队分享会",
            "event_type": "team_building",
            "description": "各部门分享近期工作心得和技术经验。",
            "scheduled_at": friday.replace(hour=10, minute=0, second=0, microsecond=0),
            "duration_minutes": 90,
            "max_participants": 50,
            "rewards_xp": 25,
            "rewards_coins": 15,
            "room_id": None,
        },
        {
            "name": "新人欢迎会",
            "event_type": "team_building",
            "description": "欢迎新同事加入公司大家庭！",
            "scheduled_at": (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0),
            "duration_minutes": 60,
            "max_participants": 20,
            "rewards_xp": 20,
            "rewards_coins": 10,
            "room_id": cafe_room_id,
        },
    ]

    created = []
    for t in templates:
        # 检查是否已存在同名同时间活动
        existing = await db.execute(
            select(CompanyEvent).where(
                CompanyEvent.name == t["name"],
                CompanyEvent.scheduled_at == t["scheduled_at"],
            )
        )
        if existing.scalar_one_or_none():
            continue

        event = CompanyEvent(
            name=t["name"],
            event_type=t["event_type"],
            description=t["description"],
            scheduled_at=t["scheduled_at"],
            duration_minutes=t["duration_minutes"],
            max_participants=t["max_participants"],
            rewards_xp=t["rewards_xp"],
            rewards_coins=t["rewards_coins"],
            room_id=t.get("room_id"),
            participants=[],
            is_active="upcoming",
        )
        db.add(event)
        created.append(t["name"])

    await db.flush()
    return {"created": created, "count": len(created)}


# 需要导入 CompanyRoom 用于生成活动
from app.models.company_room import CompanyRoom
