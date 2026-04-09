"""
任务调度引擎 - 过期任务检查与处理
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
    扫描并处理所有过期任务 - 每小时运行一次

    流程：
    1. 查找所有 status in (pending, in_progress) 且 deadline < now 的任务
    2. 标记为 expired
    3. 通过 extract_memory() 记录失败记忆
    4. 跟踪连续失败次数
    5. 如果连续3+次过期，记录警告记忆（importance=8）
    """
    now = datetime.now(timezone.utc)
    expired_count = 0
    warning_count = 0

    async with AsyncSessionLocal() as db:
        # 查找所有过期任务
        result = await db.execute(
            select(AgentTask).where(
                AgentTask.status.in_(["pending", "in_progress"]),
                AgentTask.deadline.is_not(None),
                AgentTask.deadline < now,
            )
        )
        expired_tasks = result.scalars().all()

        if not expired_tasks:
            logger.debug("无过期任务")
            return {"expired_count": 0, "warning_count": 0}

        # 按 assignee 分组处理
        tasks_by_agent: dict[int, list[AgentTask]] = {}
        for task in expired_tasks:
            if task.assignee_id not in tasks_by_agent:
                tasks_by_agent[task.assignee_id] = []
            tasks_by_agent[task.assignee_id].append(task)

        for agent_id, agent_tasks in tasks_by_agent.items():
            for task in agent_tasks:
                # 标记为过期
                task.status = "expired"
                expired_count += 1

                # 记录失败记忆
                await extract_memory(
                    db, agent_id, "task_fail",
                    f"任务「{task.title}」已过期未完成，截止时间为{task.deadline.strftime('%Y-%m-%d %H:%M')}",
                )

            # 检查连续过期次数
            consecutive_expired = await _count_consecutive_expired(db, agent_id)
            if consecutive_expired >= 3:
                warning_count += 1
                # 记录高重要度警告记忆
                from app.models.agent_memory import AgentMemory
                warning_memory = AgentMemory(
                    agent_id=agent_id,
                    content=f"警告：已连续{consecutive_expired}个任务过期未完成，工作表现需要改善！",
                    memory_type="task",
                    importance=8,
                )
                db.add(warning_memory)
                logger.warning(
                    "Agent %d 连续 %d 个任务过期，已记录警告",
                    agent_id, consecutive_expired,
                )

        await db.commit()

    logger.info("过期任务检查完成: expired=%d, warnings=%d", expired_count, warning_count)
    return {"expired_count": expired_count, "warning_count": warning_count}


async def _count_consecutive_expired(db: AsyncSession, agent_id: int) -> int:
    """
    计算Agent最近连续过期任务数量。
    从最近的任务往回数，直到遇到非expired状态的任务。
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
