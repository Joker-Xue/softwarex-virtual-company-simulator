"""
角色管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.utils.security import get_current_active_user
from app.models.user import User
from app.models.agent_profile import AgentProfile
from app.models.agent_salary_log import AgentSalaryLog
from app.schemas.agent_social import (
    AgentProfileCreate, AgentProfileUpdate, AgentProfileOut, CAREER_LEVELS,
    CAREER_PATHS, get_career_title,
)
from app.engine.schedule_engine import generate_daily_schedule
from app.engine.salary_engine import calculate_daily_salary, distribute_salaries
from app.engine.npc_seeder import seed_npcs

router = APIRouter()


def _fill_career_title(profile: AgentProfile) -> dict:
    data = {c.name: getattr(profile, c.name) for c in AgentProfile.__table__.columns}
    data["career_title"] = get_career_title(profile.career_level, profile.career_path or "management")
    # personality 可能是 dict（NPC标记）或 list，统一转为 list
    p = data.get("personality")
    if isinstance(p, dict):
        data["personality"] = list(p.get("tags", []))
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


@router.post("/profile", response_model=AgentProfileOut, summary="创建角色")
async def create_profile(
    body: AgentProfileCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "已创建角色，不可重复创建")

    total = (body.attr_communication + body.attr_leadership + body.attr_creativity
             + body.attr_technical + body.attr_teamwork + body.attr_diligence)
    if total > 300:
        raise HTTPException(400, f"属性总点数不能超过300，当前{total}")

    valid_mbti = body.mbti.upper()
    if len(valid_mbti) != 4 or not all(
        c in pair for c, pair in zip(valid_mbti, ["EI", "SN", "TF", "JP"])
    ):
        raise HTTPException(400, "无效的MBTI类型")

    profile = AgentProfile(
        user_id=user.id,
        nickname=body.nickname,
        avatar_key=body.avatar_key,
        mbti=valid_mbti,
        personality=body.personality,
        attr_communication=body.attr_communication,
        attr_leadership=body.attr_leadership,
        attr_creativity=body.attr_creativity,
        attr_technical=body.attr_technical,
        attr_teamwork=body.attr_teamwork,
        attr_diligence=body.attr_diligence,
        department=body.department,
        career_level=0,  # 强制从实习生开始
        ai_enabled=True,  # AI自主操控
        daily_schedule=generate_daily_schedule({"mbti": valid_mbti}),
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)

    # 懒初始化NPC（首次创建角色时确保公司有同事）
    try:
        async with db.begin_nested():
            await seed_npcs(db)
    except Exception:
        pass

    # 为新角色自动生成初始任务
    try:
        from app.engine.task_generator import generate_tasks_for_agent
        await generate_tasks_for_agent(profile, db)
    except Exception:
        pass

    return AgentProfileOut(**_fill_career_title(profile))


@router.get("/profile", response_model=AgentProfileOut, summary="获取自己的角色")
async def get_my_profile(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")
    return AgentProfileOut(**_fill_career_title(profile))


@router.get("/profile/{agent_id}", response_model=AgentProfileOut, summary="查看他人角色")
async def get_profile(agent_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == agent_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "角色不存在")
    return AgentProfileOut(**_fill_career_title(profile))


@router.put("/profile", response_model=AgentProfileOut, summary="更新角色信息")
async def update_profile(
    body: AgentProfileUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    await db.flush()
    await db.refresh(profile)
    return AgentProfileOut(**_fill_career_title(profile))


@router.get("/salary/info", summary="查看当前薪资信息")
async def get_salary_info(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")

    salary_info = calculate_daily_salary(profile)
    return {
        "career_level": profile.career_level,
        "career_title": CAREER_LEVELS.get(profile.career_level, {}).get("title", "未知"),
        **salary_info,
    }


@router.get("/salary/history", summary="薪资历史记录")
async def get_salary_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(7, ge=1, le=30),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")

    logs_result = await db.execute(
        select(AgentSalaryLog)
        .where(AgentSalaryLog.agent_id == profile.id)
        .order_by(AgentSalaryLog.paid_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = logs_result.scalars().all()

    return [
        {
            "id": log.id,
            "amount": log.amount,
            "salary_type": log.salary_type,
            "description": log.description,
            "paid_at": log.paid_at.isoformat() if log.paid_at else None,
        }
        for log in logs
    ]


@router.post("/salary/distribute", summary="发放日薪（管理接口）")
async def trigger_salary_distribution(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await distribute_salaries(db)
    return result


@router.post("/career-path", summary="选择职业发展路径")
async def choose_career_path(
    path: str = Query(..., pattern="^(management|technical)$"),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    当角色达到Lv.3（高级员工）时，可以选择职业路径：
    - management: 管理路线（经理→总监→CEO）
    - technical: 技术路线（技术专家→首席工程师→CTO）
    """
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "尚未创建角色")

    if profile.career_level < 3:
        raise HTTPException(400, "需要达到Lv.3（高级员工）才能选择职业路径")

    if profile.career_path:
        raise HTTPException(400, f"已选择职业路径: {profile.career_path}，不可更改")

    profile.career_path = path
    await db.flush()

    # 给出推荐理由
    tech_score = (profile.attr_technical or 50) + (profile.attr_creativity or 50)
    mgmt_score = (profile.attr_leadership or 50) + (profile.attr_communication or 50)
    recommended = "technical" if tech_score > mgmt_score else "management"

    path_titles = CAREER_PATHS[path]
    future = [path_titles[lv]["title"] for lv in sorted(path_titles.keys())]

    return {
        "career_path": path,
        "future_titles": future,
        "was_recommended": path == recommended,
        "message": f"已选择{'管理' if path == 'management' else '技术'}路线！未来晋升路径：{'→'.join(future)}",
    }
