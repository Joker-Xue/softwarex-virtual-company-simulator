"""
Agent长期记忆引擎 - 提取、存储和检索Agent记忆
"""
import logging
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_memory import AgentMemory
from app.models.agent_action_log import AgentActionLog
from app.models.agent_task import AgentTask

logger = logging.getLogger(__name__)

# 事件类型 -> 重要度映射
IMPORTANCE_MAP = {
    "promotion": 10,
    "task_complete": 7,
    "salary": 6,
    "task_fail": 5,
    "friendship": 4,
    "chat": 3,
    "move": 1,
}

# 事件类型 -> 记忆类型映射
MEMORY_TYPE_MAP = {
    "promotion": "career",
    "salary": "career",
    "task_complete": "task",
    "task_fail": "task",
    "chat": "interaction",
    "friendship": "social",
    "move": "observation",
}


async def extract_memory(
    db: AsyncSession,
    agent_id: int,
    event_type: str,
    content: str,
    related_agent_id: int | None = None,
) -> AgentMemory:
    """
    从事件中提取记忆并保存到数据库。

    Args:
        db: 数据库会话
        agent_id: Agent ID
        event_type: 事件类型 (promotion/task_complete/task_fail/chat/move/friendship/salary)
        content: 记忆内容描述
        related_agent_id: 相关Agent ID（可选）

    Returns:
        创建的 AgentMemory 记录
    """
    importance = IMPORTANCE_MAP.get(event_type, 3)
    memory_type = MEMORY_TYPE_MAP.get(event_type, "observation")

    memory = AgentMemory(
        agent_id=agent_id,
        content=content,
        memory_type=memory_type,
        importance=importance,
        related_agent_id=related_agent_id,
    )
    db.add(memory)
    await db.flush()
    await db.refresh(memory)

    logger.info(
        "Memory extracted: agent=%d type=%s importance=%d content=%s",
        agent_id, memory_type, importance, content[:50],
    )
    return memory


async def recall_memories(
    db: AsyncSession,
    agent_id: int,
    context: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """
    检索Agent的近期记忆，按重要度和时间排序。

    Args:
        db: 数据库会话
        agent_id: Agent ID
        context: 上下文过滤 (memory_type: interaction/task/observation/career/social)
        limit: 返回数量上限

    Returns:
        记忆字典列表，包含 id, content, memory_type, importance, created_at
    """
    query = select(AgentMemory).where(AgentMemory.agent_id == agent_id)

    if context:
        query = query.where(AgentMemory.memory_type == context)

    query = query.order_by(
        AgentMemory.importance.desc(),
        AgentMemory.created_at.desc(),
    ).limit(limit)

    result = await db.execute(query)
    memories = result.scalars().all()

    return [
        {
            "id": m.id,
            "content": m.content,
            "memory_type": m.memory_type,
            "importance": m.importance,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in memories
    ]


async def get_memory_summary(db: AsyncSession, agent_id: int) -> dict:
    """
    获取Agent记忆统计摘要。

    Args:
        db: 数据库会话
        agent_id: Agent ID

    Returns:
        包含 total_memories, most_common_type, highest_importance_memory 的字典
    """
    # 总记忆数
    total_result = await db.execute(
        select(sa_func.count(AgentMemory.id)).where(AgentMemory.agent_id == agent_id)
    )
    total_memories = total_result.scalar() or 0

    # 最常见记忆类型
    most_common_type = None
    if total_memories > 0:
        type_result = await db.execute(
            select(AgentMemory.memory_type, sa_func.count(AgentMemory.id).label("cnt"))
            .where(AgentMemory.agent_id == agent_id)
            .group_by(AgentMemory.memory_type)
            .order_by(sa_func.count(AgentMemory.id).desc())
            .limit(1)
        )
        row = type_result.first()
        if row:
            most_common_type = row[0]

    # 最高重要度记忆
    highest_importance_memory = None
    if total_memories > 0:
        high_result = await db.execute(
            select(AgentMemory)
            .where(AgentMemory.agent_id == agent_id)
            .order_by(AgentMemory.importance.desc(), AgentMemory.created_at.desc())
            .limit(1)
        )
        top_memory = high_result.scalar_one_or_none()
        if top_memory:
            highest_importance_memory = {
                "id": top_memory.id,
                "content": top_memory.content,
                "memory_type": top_memory.memory_type,
                "importance": top_memory.importance,
                "created_at": top_memory.created_at.isoformat() if top_memory.created_at else None,
            }

    return {
        "total_memories": total_memories,
        "most_common_type": most_common_type,
        "highest_importance_memory": highest_importance_memory,
    }


async def get_context_for_decision(db: AsyncSession, agent_id: int) -> dict:
    """
    Gather comprehensive context for LLM decision making.

    Collects recent memories, memory summary, recent actions, and pending tasks
    to provide rich context for the AI decision engine.

    Args:
        db: 数据库会话
        agent_id: Agent ID

    Returns:
        dict with keys: recent_memories, memory_summary, recent_actions, pending_task_count
    """
    # 1. 获取近期重要记忆 (top 5, 按重要度+时间排序)
    recent_memories = await recall_memories(db, agent_id, limit=5)

    # 2. 获取记忆统计摘要
    memory_summary = await get_memory_summary(db, agent_id)

    # 3. 获取近期行为日志 (最近5条)
    action_result = await db.execute(
        select(AgentActionLog)
        .where(AgentActionLog.agent_id == agent_id)
        .order_by(AgentActionLog.created_at.desc())
        .limit(5)
    )
    action_logs = action_result.scalars().all()
    recent_actions = [
        {
            "action": log.action,
            "detail": log.detail,
            "location": log.location,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in action_logs
    ]

    # 4. 获取待完成任务数
    pending_result = await db.execute(
        select(sa_func.count(AgentTask.id)).where(
            AgentTask.assignee_id == agent_id,
            AgentTask.status.in_(["pending", "in_progress"]),
        )
    )
    pending_task_count = pending_result.scalar() or 0

    # 5. 构建记忆文本摘要
    memory_text_parts = []
    for m in recent_memories:
        memory_text_parts.append(f"[{m['memory_type']}|重要度{m['importance']}] {m['content']}")
    memory_text = "\n".join(memory_text_parts) if memory_text_parts else "暂无记忆"

    summary_text = (
        f"总记忆数: {memory_summary['total_memories']}, "
        f"最常见类型: {memory_summary['most_common_type'] or '无'}"
    )
    if memory_summary.get("highest_importance_memory"):
        hm = memory_summary["highest_importance_memory"]
        summary_text += f", 最重要记忆: {hm['content'][:40]}"

    return {
        "recent_memories": recent_memories,
        "recent_memories_text": memory_text,
        "memory_summary": memory_summary,
        "memory_summary_text": summary_text,
        "recent_actions": recent_actions,
        "pending_task_count": pending_task_count,
    }
