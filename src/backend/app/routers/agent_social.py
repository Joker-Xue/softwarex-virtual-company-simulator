"""
RolemanageAPI
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
    # personality may be dict（NPCmark）or list，uniformly converted to list
    p = data.get("personality")
    if isinstance(p, dict):
        data["personality"] = list(p.get("tags", []))
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


@router.post("/profile", response_model=AgentProfileOut, summary="create profile")
async def create_profile(
    body: AgentProfileCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "already createdRole，Cannot be re-created")

    total = (body.attr_communication + body.attr_leadership + body.attr_creativity
             + body.attr_technical + body.attr_teamwork + body.attr_diligence)
    if total > 300:
        raise HTTPException(400, f"Total attribute points cannot exceed 300，Current{total}")

    valid_mbti = body.mbti.upper()
    if len(valid_mbti) != 4 or not all(
        c in pair for c, pair in zip(valid_mbti, ["EI", "SN", "TF", "JP"])
    ):
        raise HTTPException(400, "Invalid MBTItype")

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
        career_level=0,  # Force to start from Internet
        ai_enabled=True,  # AI autonomous control
        daily_schedule=generate_daily_schedule({"mbti": valid_mbti}),
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)

    # Lazy initialization of NPCs（create profileMake sure your company has a Colleague）
    try:
        async with db.begin_nested():
            await seed_npcs(db)
    except Exception:
        pass

    return AgentProfileOut(**_fill_career_title(profile))


@router.get("/profile", response_model=AgentProfileOut, summary="Get your own Role")
async def get_my_profile(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile has not been created yet")
    return AgentProfileOut(**_fill_career_title(profile))


@router.get("/profile/{agent_id}", response_model=AgentProfileOut, summary="View other people's roles")
async def get_profile(agent_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == agent_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "role does not exist")
    return AgentProfileOut(**_fill_career_title(profile))


@router.put("/profile", response_model=AgentProfileOut, summary="Update profile info")
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
        raise HTTPException(404, "Profile has not been created yet")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    await db.flush()
    await db.refresh(profile)
    return AgentProfileOut(**_fill_career_title(profile))


@router.get("/salary/info", summary="View CurrentCompensationInfo")
async def get_salary_info(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile has not been created yet")

    salary_info = calculate_daily_salary(profile)
    return {
        "career_level": profile.career_level,
        "career_title": CAREER_LEVELS.get(profile.career_level, {}).get("title", "Unknown"),
        **salary_info,
    }


@router.get("/salary/history", summary="Compensation History")
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
        raise HTTPException(404, "Profile has not been created yet")

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


@router.post("/salary/distribute", summary="Issue Daily Pay（Management interface）")
async def trigger_salary_distribution(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await distribute_salaries(db)
    return result


@router.post("/career-path", summary="Choose a career path")
async def choose_career_path(
    path: str = Query(..., pattern="^(management|technical)$"),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    When Role reaches Lv.3（Senior Staff）hour，Career paths available：
    - management: Management Track（Manager→Director→CEO）
    - technical: Technical Track（Technical Expert→Principal Engineer→CTO）
    """
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile has not been created yet")

    if profile.career_level < 3:
        raise HTTPException(400, "Need to reach Lv.3（Senior Staff）To choose a career path")

    if profile.career_path:
        raise HTTPException(400, f"Career path selected: {profile.career_path}，cannot be changed")

    profile.career_path = path
    await db.flush()

    # Give reasons for recommendation
    tech_score = (profile.attr_technical or 50) + (profile.attr_creativity or 50)
    mgmt_score = (profile.attr_leadership or 50) + (profile.attr_communication or 50)
    recommended = "technical" if tech_score > mgmt_score else "management"

    path_titles = CAREER_PATHS[path]
    future = [path_titles[lv]["title"] for lv in sorted(path_titles.keys())]

    return {
        "career_path": path,
        "future_titles": future,
        "was_recommended": path == recommended,
        "message": f"Selected{'manage' if path == 'management' else 'technology'}route！Future promotion paths：{'→'.join(future)}",
    }
