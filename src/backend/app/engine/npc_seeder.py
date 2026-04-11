"""
NPC seed data system - Create 16 AI virtual Roles，Covers 7 departments and various career levels
Department：management / engineering / product / marketing / finance / hr / operations
"""
import logging
import asyncio
from collections import Counter

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.agent_profile import AgentProfile
from app.engine.schedule_engine import generate_daily_schedule
from app.engine.named_spots import (
    assign_work_spot,
    get_anchor_spot,
    get_spot_pos,
    is_anchor_role,
)

logger = logging.getLogger(__name__)

NPC_ROSTER = [
    # ── Management Floor (3F) ──
    {
        "nickname": "Chen", "mbti": "ENTJ", "department": "management",
        "career_level": 6, "career_path": "management",
        "attrs": {"communication": 85, "leadership": 95, "creativity": 70,
                  "technical": 60, "teamwork": 75, "diligence": 80},
        "tasks_completed": 130, "xp": 6000, "floor": 3,
    },
    {
        "nickname": "Wang", "mbti": "ESTJ", "department": "management",
        "career_level": 5, "career_path": "management",
        "attrs": {"communication": 75, "leadership": 85, "creativity": 55,
                  "technical": 80, "teamwork": 70, "diligence": 90},
        "tasks_completed": 90, "xp": 3500, "floor": 3,
    },
    {
        "nickname": "Li", "mbti": "ENFJ", "department": "management",
        "career_level": 5, "career_path": "management",
        "attrs": {"communication": 90, "leadership": 80, "creativity": 85,
                  "technical": 40, "teamwork": 85, "diligence": 75},
        "tasks_completed": 85, "xp": 3200, "floor": 3,
    },
    # ── Engineering (2F) ──
    {
        "nickname": "Zhang", "mbti": "ISTJ", "department": "engineering",
        "career_level": 4, "career_path": "management",
        "attrs": {"communication": 60, "leadership": 70, "creativity": 50,
                  "technical": 85, "teamwork": 65, "diligence": 95},
        "tasks_completed": 55, "xp": 1700, "floor": 2,
    },
    {
        "nickname": "Liu", "mbti": "INTP", "department": "engineering",
        "career_level": 3, "career_path": "technical",
        "attrs": {"communication": 40, "leadership": 35, "creativity": 85,
                  "technical": 95, "teamwork": 45, "diligence": 70},
        "tasks_completed": 35, "xp": 900, "floor": 2,
    },
    {
        "nickname": "Ma", "mbti": "INFP", "department": "engineering",
        "career_level": 1, "career_path": "",
        "attrs": {"communication": 55, "leadership": 30, "creativity": 90,
                  "technical": 70, "teamwork": 60, "diligence": 50},
        "tasks_completed": 6, "xp": 120, "floor": 2,
    },
    # ── Product (2F) ──
    {
        "nickname": "Sun", "mbti": "ENFJ", "department": "product",
        "career_level": 4, "career_path": "management",
        "attrs": {"communication": 85, "leadership": 70, "creativity": 90,
                  "technical": 55, "teamwork": 80, "diligence": 75},
        "tasks_completed": 48, "xp": 1550, "floor": 2,
    },
    {
        "nickname": "Qian", "mbti": "ISFP", "department": "product",
        "career_level": 2, "career_path": "",
        "attrs": {"communication": 65, "leadership": 40, "creativity": 85,
                  "technical": 60, "teamwork": 70, "diligence": 70},
        "tasks_completed": 14, "xp": 350, "floor": 2,
    },
    # ── Marketing (2F) ──
    {
        "nickname": "Zhou", "mbti": "ENFP", "department": "marketing",
        "career_level": 3, "career_path": "technical",
        "attrs": {"communication": 85, "leadership": 60, "creativity": 90,
                  "technical": 40, "teamwork": 80, "diligence": 55},
        "tasks_completed": 33, "xp": 850, "floor": 2,
    },
    {
        "nickname": "Zheng", "mbti": "ESFP", "department": "marketing",
        "career_level": 2, "career_path": "",
        "attrs": {"communication": 85, "leadership": 50, "creativity": 75,
                  "technical": 35, "teamwork": 80, "diligence": 60},
        "tasks_completed": 16, "xp": 380, "floor": 2,
    },
    # ── Finance (2F) ──
    {
        "nickname": "Wu", "mbti": "ISTP", "department": "finance",
        "career_level": 2, "career_path": "",
        "attrs": {"communication": 45, "leadership": 40, "creativity": 55,
                  "technical": 80, "teamwork": 50, "diligence": 85},
        "tasks_completed": 18, "xp": 400, "floor": 2,
    },
    {
        "nickname": "Lin", "mbti": "ENTP", "department": "finance",
        "career_level": 1, "career_path": "",
        "attrs": {"communication": 75, "leadership": 50, "creativity": 80,
                  "technical": 65, "teamwork": 55, "diligence": 45},
        "tasks_completed": 5, "xp": 110, "floor": 2,
    },
    # ── HR Department (1F) ──
    {
        "nickname": "Zhao", "mbti": "ESFJ", "department": "hr",
        "career_level": 4, "career_path": "management",
        "attrs": {"communication": 90, "leadership": 75, "creativity": 60,
                  "technical": 35, "teamwork": 90, "diligence": 80},
        "tasks_completed": 52, "xp": 1600, "floor": 1,
    },
    {
        "nickname": "Huang", "mbti": "ISFJ", "department": "hr",
        "career_level": 1, "career_path": "",
        "attrs": {"communication": 70, "leadership": 45, "creativity": 40,
                  "technical": 35, "teamwork": 85, "diligence": 90},
        "tasks_completed": 7, "xp": 130, "floor": 1,
    },
    # ── Operations (2F) ──
    {
        "nickname": "Lv", "mbti": "ESTP", "department": "operations",
        "career_level": 3, "career_path": "technical",
        "attrs": {"communication": 80, "leadership": 55, "creativity": 70,
                  "technical": 60, "teamwork": 75, "diligence": 65},
        "tasks_completed": 30, "xp": 820, "floor": 2,
    },
    {
        "nickname": "Han", "mbti": "INFJ", "department": "operations",
        "career_level": 1, "career_path": "",
        "attrs": {"communication": 70, "leadership": 35, "creativity": 75,
                  "technical": 45, "teamwork": 80, "diligence": 75},
        "tasks_completed": 4, "xp": 95, "floor": 2,
    },
]

# 2F new layout（600x600canvas）:
#   left column(full height): Engineering  x=0,   y=50,  w=200, h=450  center=(100, 275)
#   Upper middle column: Marketing x=220, y=50,  w=180, h=210  center=(310, 155)
#   Bottom middle column: Product x=220, y=280, w=180, h=220  center=(310, 390)
#   On the right column: Finance x=420, y=50,  w=180, h=210  center=(510, 155)
#   Bottom right column: Operations x=420, y=280, w=180, h=220  center=(510, 390)
# pos_y use floor offset coding: floor1=+0, floor2=+700, floor3=+1400

FLOOR2_DEPT_CENTERS = {
    "engineering": (100, 975),   # 275 + 700
    "marketing":   (310, 855),   # 155 + 700
    "product":     (310, 1090),  # 390 + 700
    "finance":     (510, 855),   # 155 + 700
    "operations":  (510, 1090),  # 390 + 700
}

FLOOR1_DEPT_CENTERS = {
    "hr": (510, 300),
}

# Floor 3: CEO office, director office, meeting room
FLOOR3_CENTER_CEO = (510, 1700)
FLOOR3_CENTER_DIRECTOR = (300, 1700)
FLOOR3_CENTER_MEETING = (90, 1700)


def _npc_position(npc: dict) -> tuple[int, int]:
    """Calculate spawn position for an NPC using named spots."""
    career_level = npc.get("career_level", 1)
    career_path = npc.get("career_path", "")
    dept = npc.get("department", "engineering")
    # Use index=0 as fallback; seed_npcs passes roster_index
    roster_index = npc.get("_roster_index", 0)

    # CEO/Directors → anchor spot in their office
    if is_anchor_role(career_level, dept, career_path):
        anchor = get_anchor_spot(career_level, dept, career_path)
        if anchor:
            return get_spot_pos(anchor)

    # Regular employees → their department work desk
    spot = assign_work_spot(dept, roster_index)
    if spot:
        return get_spot_pos(spot)

    # Fallback: lobby reception
    from app.engine.named_spots import get_spot_pos as gsp
    return gsp("lobby_reception")


async def _npcs_already_seeded(db: AsyncSession) -> bool:
    """Check if NPC profiles already exist."""
    result = await db.execute(
        select(AgentProfile).limit(200)
    )
    profiles = result.scalars().all()
    return any(_is_npc_profile(p) for p in profiles)


def _is_npc_profile(profile: AgentProfile) -> bool:
    """compatible history structure to identify NPCs."""
    if str(profile.avatar_key or "").startswith("npc_"):
        return True
    personality = profile.personality
    if isinstance(personality, dict):
        return bool(personality.get("is_npc"))
    if isinstance(personality, list):
        for item in personality:
            if isinstance(item, dict) and item.get("is_npc"):
                return True
    return False


def _build_distribution(rows: list[tuple[int, str, int, int, bool]]) -> dict:
    """
    rows item: (id, department, pos_x, pos_y, is_online)
    """
    floor_counter = Counter()
    dept_counter = Counter()
    floor_dept_counter = Counter()
    hotspot_counter = Counter()
    online_total = 0

    for _id, dept, pos_x, pos_y, is_online in rows:
        if not is_online:
            continue
        online_total += 1
        floor = pos_y // 700 + 1
        dept_name = dept or "unknown"
        floor_counter[floor] += 1
        dept_counter[dept_name] += 1
        floor_dept_counter[(floor, dept_name)] += 1
        hotspot_counter[(pos_x, pos_y)] += 1

    hotspots = []
    for (x, y), count in hotspot_counter.most_common(5):
        ratio = round(count / online_total, 4) if online_total > 0 else 0.0
        hotspots.append({"x": x, "y": y, "count": count, "ratio": ratio})

    by_floor = dict(sorted(floor_counter.items()))
    return {
        "online_total": online_total,
        "by_floor": by_floor,
        "online_by_floor": by_floor,
        "by_department": dict(sorted(dept_counter.items())),
        "by_floor_department": {
            f"{floor}F-{dept}": count
            for (floor, dept), count in sorted(floor_dept_counter.items())
        },
        "hotspots": hotspots,
    }


async def get_simulation_distribution(db: AsyncSession) -> dict:
    """
    Get the "World Visible Role" distribution：
    - online players
    - anchoredNPC（Not affected by is_online dirty state）
    """
    result = await db.execute(select(AgentProfile))
    profiles = result.scalars().all()
    rows: list[tuple[int, str, int, int, bool]] = []
    for p in profiles:
        is_visible = bool(p.is_online) or _is_npc_profile(p)
        rows.append(
            (
                int(p.id or 0),
                p.department or "unknown",
                int(p.pos_x or 0),
                int(p.pos_y or 0),
                is_visible,
            )
        )
    return _build_distribution(rows)


async def seed_npcs(db: AsyncSession) -> int:
    """
    Seed NPC agents into the database. Idempotent - skips if NPCs exist.
    Returns the number of NPCs created.
    """
    if await _npcs_already_seeded(db):
        logger.info("NPCs already seeded, skipping.")
        return 0

    created = 0
    for i, npc in enumerate(NPC_ROSTER):
        username = "npc_" + npc["nickname"]
        email = "npc_" + str(i) + "@virtual.local"

        # Reuse existing user if a stale npc account already exists.
        user_row = await db.execute(select(User).where(User.username == username))
        user = user_row.scalar_one_or_none()
        if user is None:
            user = User(
                username=username,
                email=email,
                password_hash="npc_no_login",
                is_active=True,
                is_admin=False,
            )
            db.add(user)
            await db.flush()  # get user.id

        # Skip if this user already has an NPC profile.
        profile_row = await db.execute(select(AgentProfile).where(AgentProfile.user_id == user.id))
        existed_profile = profile_row.scalar_one_or_none()
        if existed_profile:
            if _is_npc_profile(existed_profile):
                continue
            # Avoid corrupting a non-NPC account that accidentally uses npc_ username.
            logger.warning("Skip NPC seed for username=%s: existing non-NPC profile user_id=%s", username, user.id)
            continue

        # Calculate spawn position using named spots
        npc_with_index = {**npc, "_roster_index": i}
        pos_x, pos_y = _npc_position(npc_with_index)

        # Generate daily schedule
        schedule = generate_daily_schedule({"mbti": npc["mbti"]})

        attrs = npc["attrs"]
        profile = AgentProfile(
            user_id=user.id,
            nickname=npc["nickname"],
            avatar_key="npc_" + str(i),
            mbti=npc["mbti"],
            personality={"is_npc": True, "roster_index": i},
            attr_communication=attrs["communication"],
            attr_leadership=attrs["leadership"],
            attr_creativity=attrs["creativity"],
            attr_technical=attrs["technical"],
            attr_teamwork=attrs["teamwork"],
            attr_diligence=attrs["diligence"],
            career_level=npc["career_level"],
            career_path=npc.get("career_path", ""),
            department=npc["department"],
            tasks_completed=npc["tasks_completed"],
            xp=npc["xp"],
            pos_x=pos_x,
            pos_y=pos_y,
            current_action="idle",
            is_online=True,
            ai_enabled=True,
            daily_schedule=schedule,
        )
        db.add(profile)
        created += 1
        logger.info("Seeded NPC: %s (level %d, %s)", npc["nickname"], npc["career_level"], npc["department"])

    await db.commit()
    logger.info("NPC seeding complete: %d agents created.", created)
    return created


async def seed_npcs_standalone():
    """Standalone entry point - creates its own DB session."""
    async with AsyncSessionLocal() as db:
        return await seed_npcs(db)


async def reset_npc_positions(db: AsyncSession) -> int:
    """
    Reset all AI Roles to corresponding semantic seats（use named_spots system）。
    Called when the server starts，Fix random coordinates in old Database。
    """
    from app.engine.agent_ai import clear_room_cache
    clear_room_cache()

    result = await db.execute(
        select(AgentProfile).where(AgentProfile.ai_enabled == True)
    )
    agents = result.scalars().all()

    updated = 0
    for agent in agents:
        dept = (agent.department or "").strip()
        career_level = agent.career_level or 0

        if is_anchor_role(career_level, dept, agent.career_path or ""):
            anchor = get_anchor_spot(career_level, dept, agent.career_path or "")
            if anchor:
                agent.pos_x, agent.pos_y = get_spot_pos(anchor)
                updated += 1
                continue

        spot = assign_work_spot(dept, agent.id or 0)
        if spot:
            agent.pos_x, agent.pos_y = get_spot_pos(spot)
        else:
            # UnknownDepartment → Lobby reception
            from app.engine.named_spots import get_spot_pos as gsp
            agent.pos_x, agent.pos_y = gsp("lobby_reception")
        updated += 1

    await db.commit()
    logger.info("reset_npc_positions: repositioned %d AI agents to named spots", updated)
    return updated


async def rebuild_npcs(db: AsyncSession) -> dict:
    """
    Rebuild NPCdata at once：
    1) Delete existing NPC（NPCs only）
    2) Press ROSTER to reseed
    3) Perform semantic point rearrangement
    4) Backstatistical report
    """
    for attempt in range(3):
        try:
            result = await db.execute(select(AgentProfile))
            profiles = result.scalars().all()
            npc_profiles = [p for p in profiles if _is_npc_profile(p)]
            npc_user_ids = [p.user_id for p in npc_profiles]
            deleted_npc_profiles = len(npc_profiles)

            for profile in npc_profiles:
                await db.delete(profile)
            await db.flush()

            if npc_user_ids:
                user_rows = await db.execute(select(User).where(User.id.in_(npc_user_ids)))
                npc_users = user_rows.scalars().all()
                for user in npc_users:
                    await db.delete(user)
            await db.commit()

            # Recreate NPCs using existing idempotent seed logic
            created_npc = await seed_npcs(db)
            repositioned = await reset_npc_positions(db)

            stat_rows = await db.execute(
                select(
                    AgentProfile.id,
                    AgentProfile.department,
                    AgentProfile.pos_x,
                    AgentProfile.pos_y,
                    AgentProfile.is_online,
                )
            )
            rows = [
                row for row in stat_rows.all()
                if isinstance(row[0], int)
            ]
            distribution = _build_distribution(rows)
            report = {
                "deleted_npc_profiles": deleted_npc_profiles,
                "deleted_npc_users": len(npc_user_ids),
                "created_npc_profiles": created_npc,
                "repositioned_profiles": repositioned,
                "distribution": distribution,
            }
            logger.info("NPC rebuild completed: %s", report)
            return report
        except DBAPIError as e:
            await db.rollback()
            if "DeadlockDetectedError" in str(e) and attempt < 2:
                wait_seconds = 0.2 * (attempt + 1)
                logger.warning("rebuild_npcs deadlock detected, retry in %.1fs", wait_seconds)
                await asyncio.sleep(wait_seconds)
                continue
            raise
