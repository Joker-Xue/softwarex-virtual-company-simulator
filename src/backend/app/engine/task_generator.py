"""
Task generator - personalized task generation (hybrid LLM + deterministic fallback)
"""
import re
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_profile import AgentProfile
from app.models.agent_task import AgentTask
from app.utils.llm import call_llm_json
from app.prompts.agent_prompt import TASK_GENERATION_PROMPT, TASK_GENERATION_PROMPT_V2


TASK_TEMPLATES = {
    "engineering": [
        {"title": "Refactor API Endpoints", "description": "Improve the structure of an existing API module", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "Engineering Office", "contact": "Liu"},
        {"title": "Write Unit Tests", "description": "Add test coverage for a core module", "difficulty": 2, "xp_reward": 30, "tag": "technical", "location": "Engineering Office", "contact": "Ma"},
        {"title": "Review Technical Proposal", "description": "Review the implementation plan for a new feature", "difficulty": 2, "xp_reward": 25, "tag": "creative", "location": "Meeting Room", "contact": "Wang"},
        {"title": "Performance Tuning", "description": "Improve service response time", "difficulty": 4, "xp_reward": 50, "tag": "technical", "location": "Engineering Office", "contact": "Liu"},
        {"title": "Coach New Hire", "description": "Help a new teammate understand the codebase", "difficulty": 2, "xp_reward": 30, "tag": "social", "location": "Engineering Office", "contact": "Ma"},
    ],
    "marketing": [
        {"title": "Write Launch Copy", "description": "Draft marketing copy for a new feature", "difficulty": 2, "xp_reward": 25, "tag": "creative", "location": "Marketing Office", "contact": "Zhou"},
        {"title": "Analyze User Data", "description": "Review this week's user behavior data", "difficulty": 3, "xp_reward": 35, "tag": "technical", "location": "Marketing Office", "contact": "Li"},
        {"title": "Plan Campaign", "description": "Design next month's online promotion plan", "difficulty": 3, "xp_reward": 40, "tag": "creative", "location": "Meeting Room", "contact": "Li"},
        {"title": "Coordinate KOL Outreach", "description": "Reach out to creators for campaign collaboration", "difficulty": 3, "xp_reward": 40, "tag": "social", "location": "Cafe", "contact": "Zheng"},
        {"title": "Produce Promo Video", "description": "Shoot and edit a short product promo clip", "difficulty": 4, "xp_reward": 50, "tag": "creative", "location": "Marketing Office", "contact": "Zheng"},
    ],
    "finance": [
        {"title": "Monthly Finance Report", "description": "Consolidate this month's income and expenses", "difficulty": 2, "xp_reward": 30, "tag": "technical", "location": "Finance Office", "contact": "Wu"},
        {"title": "Budget Approval", "description": "Review departmental budget requests", "difficulty": 3, "xp_reward": 35, "tag": "technical", "location": "Meeting Room", "contact": "Chen"},
        {"title": "Tax Compliance Check", "description": "Review materials for tax compliance", "difficulty": 4, "xp_reward": 50, "tag": "technical", "location": "Finance Office", "contact": "Wu"},
        {"title": "Expense Policy Workshop", "description": "Explain reimbursement rules to each department", "difficulty": 2, "xp_reward": 25, "tag": "social", "location": "Meeting Room", "contact": "Zhao"},
        {"title": "Risk Assessment Report", "description": "Write a financial risk assessment", "difficulty": 4, "xp_reward": 55, "tag": "creative", "location": "Finance Office", "contact": "Wu"},
    ],
    "hr": [
        {"title": "Screen Resumes", "description": "Review resumes received this week", "difficulty": 1, "xp_reward": 15, "tag": "technical", "location": "HR Office", "contact": "Huang"},
        {"title": "Plan Team Building", "description": "Design this month's team-building event", "difficulty": 2, "xp_reward": 30, "tag": "creative", "location": "Cafe", "contact": "Zhao"},
        {"title": "Onboarding Plan", "description": "Create an onboarding plan for new hires", "difficulty": 3, "xp_reward": 35, "tag": "creative", "location": "Meeting Room", "contact": "Zhao"},
        {"title": "Interview Candidates", "description": "Interview three shortlisted candidates", "difficulty": 3, "xp_reward": 35, "tag": "social", "location": "Meeting Room", "contact": "Zhao"},
        {"title": "Update Staff Handbook", "description": "Refresh the company handbook", "difficulty": 2, "xp_reward": 25, "tag": "creative", "location": "HR Office", "contact": "Huang"},
    ],
    "product": [
        {"title": "Requirements Review", "description": "Lead this week's product requirements review", "difficulty": 3, "xp_reward": 35, "tag": "creative", "location": "Meeting Room", "contact": "Sun"},
        {"title": "Write PRD", "description": "Draft a product requirements document", "difficulty": 3, "xp_reward": 40, "tag": "creative", "location": "Product Office", "contact": "Sun"},
        {"title": "UX Research", "description": "Collect feedback through a user experience survey", "difficulty": 2, "xp_reward": 30, "tag": "technical", "location": "Product Office", "contact": "Qian"},
        {"title": "Cross-Team Alignment", "description": "Align priorities with product and engineering", "difficulty": 2, "xp_reward": 30, "tag": "social", "location": "Meeting Room", "contact": "Qian"},
        {"title": "Roadmap Update", "description": "Refresh the annual product roadmap", "difficulty": 4, "xp_reward": 50, "tag": "creative", "location": "Product Office", "contact": "Sun"},
    ],
    "operations": [
        {"title": "Daily Active Monitoring", "description": "Review today's active-user metrics", "difficulty": 1, "xp_reward": 20, "tag": "technical", "location": "Operations Office", "contact": "Han"},
        {"title": "Campaign Execution", "description": "Plan and run this week's operations event", "difficulty": 3, "xp_reward": 40, "tag": "creative", "location": "Operations Office", "contact": "Lv"},
        {"title": "Community Support", "description": "Maintain the user community and answer questions", "difficulty": 1, "xp_reward": 20, "tag": "social", "location": "Cafe", "contact": "Han"},
        {"title": "Weekly Ops Report", "description": "Summarize this week's key metrics", "difficulty": 2, "xp_reward": 30, "tag": "technical", "location": "Operations Office", "contact": "Lv"},
        {"title": "Growth Experiment", "description": "Design and launch a growth experiment", "difficulty": 4, "xp_reward": 55, "tag": "creative", "location": "Operations Office", "contact": "Lv"},
    ],
    "management": [
        {"title": "Monthly Business Review", "description": "Lead the monthly company review meeting", "difficulty": 4, "xp_reward": 60, "tag": "management", "location": "CEO Office", "contact": "Chen"},
        {"title": "Strategy Discussion", "description": "Discuss quarterly strategy with department leaders", "difficulty": 5, "xp_reward": 70, "tag": "management", "location": "Meeting Room", "contact": "Chen"},
        {"title": "Executive Weekly Sync", "description": "Host the weekly executive sync", "difficulty": 3, "xp_reward": 40, "tag": "social", "location": "Meeting Room", "contact": "Chen"},
        {"title": "Culture Initiative", "description": "Drive company values and culture programs", "difficulty": 3, "xp_reward": 40, "tag": "creative", "location": "Lobby", "contact": "Chen"},
        {"title": "Major Budget Decision", "description": "Approve large cross-department budget requests", "difficulty": 4, "xp_reward": 55, "tag": "management", "location": "CEO Office", "contact": "Chen"},
    ],
}

# Difficulty and reward scaling by level
_LEVEL_SCALING = {
    (0, 1): {"diff_add": 0, "xp_mult": 1.0},
    (2, 3): {"diff_add": 1, "xp_mult": 1.5},
    (4, 6): {"diff_add": 2, "xp_mult": 2.0},
}

# Combo bonus configuration
CHAIN_BONUS = {
    2: {"xp_mult": 1.1, "label": "Double Combo"},   # 2 in a row Same type
    3: {"xp_mult": 1.25, "label": "Triple Combo"},  # 3 in a row Same type
    4: {"xp_mult": 1.5, "label": "Mega Combo"},  # 4+ in a row
}


def _get_scaling(career_level: int) -> dict:
    for (lo, hi), scaling in _LEVEL_SCALING.items():
        if lo <= career_level <= hi:
            return scaling
    return {"diff_add": 0, "xp_mult": 1.0}


async def _get_task_history(db: AsyncSession, agent_id: int) -> dict:
    """Collect task completion history for an agent."""
    # Total completed tasks
    completed_result = await db.execute(
        select(sa_func.count(AgentTask.id)).where(
            AgentTask.assignee_id == agent_id,
            AgentTask.status == "completed",
        )
    )
    completed_count = completed_result.scalar() or 0

    # Total tasks including pending and expired
    total_result = await db.execute(
        select(sa_func.count(AgentTask.id)).where(
            AgentTask.assignee_id == agent_id,
        )
    )
    total_count = total_result.scalar() or 0

    completion_rate = int((completed_count / total_count * 100) if total_count > 0 else 100)

    # Titles of the latest 5 completed tasks, used for combo detection
    recent_result = await db.execute(
        select(AgentTask.title, AgentTask.task_type)
        .where(
            AgentTask.assignee_id == agent_id,
            AgentTask.status == "completed",
        )
        .order_by(AgentTask.completed_at.desc())
        .limit(5)
    )
    recent_tasks = [{"title": row[0], "task_type": row[1]} for row in recent_result.all()]

    return {
        "completed_count": completed_count,
        "total_count": total_count,
        "completion_rate": completion_rate,
        "recent_tasks": recent_tasks,
    }


def _detect_chain(recent_tasks: list[dict], templates: list[dict]) -> dict:
    """
    detect task combos：The number of consecutive completions of typeTask with the same label.
    Back chain_count, chain_tag, bonus_info。
    """
    if not recent_tasks:
        return {"chain_count": 0, "chain_tag": None, "bonus": None}

    # Simple chain detection：Check whether the recent task title is in the same template tag
    # try to match the tag of the most recent Task
    title_to_tag = {}
    for t in templates:
        title_to_tag[t["title"]] = t.get("tag", "technical")

    if not recent_tasks:
        return {"chain_count": 0, "chain_tag": None, "bonus": None}

    # Use the newest task as the combo baseline
    first_tag = title_to_tag.get(recent_tasks[0].get("title"), None)
    if not first_tag:
        return {"chain_count": 0, "chain_tag": None, "bonus": None}

    chain_count = 0
    for task in recent_tasks:
        tag = title_to_tag.get(task.get("title"), None)
        if tag == first_tag:
            chain_count += 1
        else:
            break

    if chain_count < 2:
        return {"chain_count": 0, "chain_tag": None, "bonus": None}

    # Apply the matching combo bonus
    bonus_key = min(chain_count, 4)
    bonus = CHAIN_BONUS.get(bonus_key, CHAIN_BONUS[4])

    return {
        "chain_count": chain_count,
        "chain_tag": first_tag,
        "bonus": bonus,
    }


def _build_personalized_tasks(
    profile: AgentProfile,
    count: int = 3,
    chain_info: dict | None = None,
    completion_rate: int = 100,
) -> list[dict]:
    """Generate deterministic personalized tasks with department pools, level scaling, combo support, and adaptive difficulty."""
    dept = profile.department
    templates = TASK_TEMPLATES.get(dept, TASK_TEMPLATES["engineering"])
    scaling = _get_scaling(profile.career_level or 0)

    # Prefer technical tasks for high technical skill, otherwise prefer creative tasks
    tech = profile.attr_technical or 50
    crea = profile.attr_creativity or 50
    prefer_tag = "technical" if tech >= crea else "creative"

    # Adaptive difficulty adjustment
    diff_adjust = 0
    if completion_rate < 40:
        diff_adjust = -1  # Lower difficulty when completion rate is low
    elif completion_rate > 85:
        diff_adjust = 1   # Raise difficulty when completion rate is high

    sorted_templates = sorted(
        templates,
        key=lambda t: (0 if t.get("tag") == prefer_tag else 1, random.random()),
    )

    # If a combo is active, prefer a task with the same tag first
    selected = []
    if chain_info and chain_info.get("chain_tag"):
        chain_tag = chain_info["chain_tag"]
        chain_candidates = [t for t in sorted_templates if t.get("tag") == chain_tag]
        if chain_candidates:
            selected.append(chain_candidates[0])
            sorted_templates = [t for t in sorted_templates if t["title"] != chain_candidates[0]["title"]]

    remaining = count - len(selected)
    selected.extend(sorted_templates[:remaining])

    results = []
    for i, t in enumerate(selected):
        difficulty = max(1, min(5, t["difficulty"] + scaling["diff_add"] + diff_adjust))
        xp_reward = int(t["xp_reward"] * scaling["xp_mult"])

        # Apply combo bonus to the first task
        is_chain = False
        if i == 0 and chain_info and chain_info.get("bonus"):
            xp_reward = int(xp_reward * chain_info["bonus"]["xp_mult"])
            is_chain = True

        results.append({
            "title": t["title"],
            "description": t["description"],
            "difficulty": difficulty,
            "xp_reward": xp_reward,
            "tag": t.get("tag", "technical"),
            "location": t.get("location", "Office"),
            "contact": t.get("contact", "Supervisor"),
            "is_chain": is_chain,
        })
    return results


def _parse_llm_tasks(llm_result, fallback_tasks: list[dict]) -> list[dict]:
    """Parse LLM-generated tasks and fall back if the format is invalid."""
    if isinstance(llm_result, dict) and "error" in llm_result:
        return fallback_tasks

    tasks_list = llm_result if isinstance(llm_result, list) else llm_result.get("tasks", [])
    if not isinstance(tasks_list, list) or len(tasks_list) == 0:
        return fallback_tasks

    parsed = []
    for item in tasks_list:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if not title:
            continue
        parsed.append({
            "title": str(title),
            "description": str(item.get("description", "")),
            "difficulty": max(1, min(5, int(item.get("difficulty", 2)))),
            "xp_reward": max(10, min(100, int(item.get("xp_reward", 20)))),
            "tag": str(item.get("tag", "technical")),
            "is_chain": bool(item.get("is_chain", False)),
            # These fields come from deterministic fallback data
            "location": "",
            "contact": "",
        })
    return parsed if parsed else fallback_tasks


async def generate_tasks_for_agent(
    profile: AgentProfile, db: AsyncSession, count: int = 3, use_llm: bool = True
) -> list[AgentTask]:
    """Generate daily tasks for a character with hybrid logic, combo bonuses, and adaptive difficulty."""
    from app.schemas.agent_social import CAREER_LEVELS

    career_title = CAREER_LEVELS.get(profile.career_level or 0, {}).get("title", "Intern")

    # Load task history
    task_history = await _get_task_history(db, profile.id)
    completion_rate = task_history["completion_rate"]

    # Detect active combo bonuses
    dept = profile.department or "engineering"
    templates = TASK_TEMPLATES.get(dept, TASK_TEMPLATES["engineering"])
    chain_info = _detect_chain(task_history["recent_tasks"], templates)

    # Deterministic fallback tasks with combo and adaptive difficulty
    fallback = _build_personalized_tasks(
        profile, count,
        chain_info=chain_info,
        completion_rate=completion_rate,
    )

    task_data = fallback
    if use_llm:
        try:
            # Build a readable task history summary
            history_text = "No recent history" if not task_history["recent_tasks"] else "\n".join(
                f"- {t['title']}" for t in task_history["recent_tasks"][:5]
            )

            # Build combo bonus summary text
            if chain_info.get("bonus"):
                chain_text = (
                    f"Completed {chain_info['chain_count']} {chain_info['chain_tag']} tasks in a row，"
                    f"triggering {chain_info['bonus']['label']} bonus（XP x{chain_info['bonus']['xp_mult']}），"
                    f"so generating a similar task can extend the combo."
                )
            else:
                chain_text = "No Task chain bonus yet"

            # Recommended difficulty
            career_level = profile.career_level or 0
            recommended_difficulty = min(5, max(1, career_level + 1))

            prompt = TASK_GENERATION_PROMPT_V2.format(
                department=dept,
                career_title=career_title,
                count=count,
                mbti=profile.mbti or "ISTJ",
                attr_technical=profile.attr_technical or 50,
                attr_creativity=profile.attr_creativity or 50,
                tasks_completed=task_history["completed_count"],
                completion_rate=completion_rate,
                task_history=history_text,
                chain_bonus_info=chain_text,
                career_level=career_level,
                recommended_difficulty=recommended_difficulty,
            )
            llm_result = await call_llm_json(prompt, cache_prefix="agent_task_v2")
            task_data = _parse_llm_tasks(llm_result, fallback)
        except Exception:
            task_data = fallback

    tasks = []
    for i, t in enumerate(task_data[:count]):
        description = t["description"]
        # Pull location and contact from fallback data because the LLM does not emit them
        fb = fallback[i] if i < len(fallback) else {}
        location = t.get("location") or fb.get("location", "Office")
        contact = t.get("contact") or fb.get("contact", "Supervisor")

        # Mark combo tasks
        if t.get("is_chain") and chain_info.get("bonus"):
            description = f"[{chain_info['bonus']['label']}] {description}"

        # Encode location and contact into the description prefix for frontend parsing
        full_description = f"[Location:{location}|Contact:{contact}] {description}"

        task = AgentTask(
            title=t["title"],
            description=full_description,
            task_type="daily",
            difficulty=t["difficulty"],
            xp_reward=t["xp_reward"],
            assignee_id=profile.id,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(task)
        tasks.append(task)

    return tasks
