"""
Task scheduling engine - expired task inspection and processing
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update as sql_update, func as sa_func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.agent_task import AgentTask
from app.models.agent_profile import AgentProfile
from app.engine.memory_engine import extract_memory

logger = logging.getLogger(__name__)


async def check_expired_tasks() -> dict:
    """
    Scan and process all expired tasks - run once per hour

    process：
    1. Find all status in (pending, in_progress) Task with deadline < now
    2. mark is expired
    3. by extract_memory() record failed memories
    4. Track the number of consecutive failures
    5. If it expires 3+ times in a row，Record warning Memories（importance=8）
    """
    now = datetime.now(timezone.utc)
    expired_count = 0
    warning_count = 0

    async with AsyncSessionLocal() as db:
        # Find all expired tasks
        result = await db.execute(
            select(AgentTask).where(
                AgentTask.status.in_(["pending", "in_progress"]),
                AgentTask.deadline.is_not(None),
                AgentTask.deadline < now,
            )
        )
        expired_tasks = result.scalars().all()

        if not expired_tasks:
            logger.debug("No expired tasks")
            return {"expired_count": 0, "warning_count": 0}

        # Group processing by assignee
        tasks_by_agent: dict[int, list[AgentTask]] = {}
        for task in expired_tasks:
            if task.assignee_id not in tasks_by_agent:
                tasks_by_agent[task.assignee_id] = []
            tasks_by_agent[task.assignee_id].append(task)

        for agent_id, agent_tasks in tasks_by_agent.items():
            for task in agent_tasks:
                # mark is expired
                task.status = "expired"
                expired_count += 1

                # record failed memories
                await extract_memory(
                    db, agent_id, "task_fail",
                    f"Task「{task.title}」Expired and not completed，The deadline is {task.deadline.strftime('%Y-%m-%d %H:%M')}",
                )

            # Check the number of consecutive expirations
            consecutive_expired = await _count_consecutive_expired(db, agent_id)
            if consecutive_expired >= 3:
                warning_count += 1
                # Record high-severity warning Memories
                from app.models.agent_memory import AgentMemory
                warning_memory = AgentMemory(
                    agent_id=agent_id,
                    content=f"warn：{consecutive_expired} consecutive tasks have expired and have not been completed.，Work performance needs improvement！",
                    memory_type="task",
                    importance=8,
                )
                db.add(warning_memory)
                logger.warning(
                    "Agent %d %d consecutive tasks expired，Warning logged",
                    agent_id, consecutive_expired,
                )

        await db.commit()

    logger.info("Expired Task check completed: expired=%d, warnings=%d", expired_count, warning_count)
    return {"expired_count": expired_count, "warning_count": warning_count}


async def _count_consecutive_expired(db: AsyncSession, agent_id: int) -> int:
    """
    Calculate the number of recent consecutive expired tasks of the Agent。
    Count backward from the most recent Task，Until a task in a non-expired state is encountered。
    """
    result = await db.execute(
        select(AgentTask.status)
        .where(AgentTask.assignee_id == agent_id)
        .order_by(AgentTask.created_at.desc())
        .limit(20)
    )
    statuses = [row[0] for row in result.fetchall()]

    consecutive = 0
    for s in statuses:
        if s == "expired":
            consecutive += 1
        else:
            break

    return consecutive
