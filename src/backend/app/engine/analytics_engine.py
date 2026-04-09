"""
行为分析引擎 - 分析Agent行为模式并生成洞察
"""
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from sqlalchemy import select, func as sa_func, cast, Date, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_profile import AgentProfile
from app.models.agent_action_log import AgentActionLog
from app.models.agent_task import AgentTask
from app.models.agent_friendship import AgentFriendship
from app.models.agent_message import AgentMessage

logger = logging.getLogger(__name__)


async def get_behavior_pattern(db: AsyncSession, agent_id: int) -> dict:
    """
    分析Agent近30天的行为模式。

    Returns:
        {
            "activity_heatmap": [[hour, day, count], ...],
            "action_distribution": {"work": 40, "chat": 25, ...},
            "insights": ["社交活跃度偏低...", ...],
            "mbti_comparison": {"my_work_pct": 40, "avg_work_pct": 35, ...}
        }
    """
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    # ── 每小时活跃度热力图 ──
    heatmap_result = await db.execute(
        select(
            extract("hour", AgentActionLog.created_at).label("hour"),
            extract("dow", AgentActionLog.created_at).label("dow"),
            sa_func.count(AgentActionLog.id).label("count"),
        )
        .where(
            AgentActionLog.agent_id == agent_id,
            AgentActionLog.created_at >= thirty_days_ago,
        )
        .group_by(
            extract("hour", AgentActionLog.created_at),
            extract("dow", AgentActionLog.created_at),
        )
    )
    activity_heatmap = [
        [int(row.hour or 0), int(row.dow or 0), row.count]
        for row in heatmap_result.all()
    ]

    # ── 行为偏好分布 ──
    action_result = await db.execute(
        select(
            AgentActionLog.action,
            sa_func.count(AgentActionLog.id).label("count"),
        )
        .where(
            AgentActionLog.agent_id == agent_id,
            AgentActionLog.created_at >= thirty_days_ago,
        )
        .group_by(AgentActionLog.action)
    )
    action_distribution = {row.action: row.count for row in action_result.all()}
    total_actions = sum(action_distribution.values()) or 1

    # ── 行为百分比 ──
    action_pct = {
        action: round(count / total_actions * 100, 1)
        for action, count in action_distribution.items()
    }

    # ── 个性化建议 ──
    insights = []
    work_pct = action_pct.get("work", 0)
    chat_pct = action_pct.get("chat", 0)
    rest_pct = action_pct.get("rest", 0)
    meeting_pct = action_pct.get("meeting", 0)

    if chat_pct < 15:
        insights.append("你的社交活动偏少，建议多参加公司活动或与同事聊天，提升人脉关系")
    if work_pct > 60:
        insights.append("你的工作强度较高，注意劳逸结合，适当休息可以提升效率")
    if rest_pct < 10:
        insights.append("休息时间不足，建议定期去咖啡厅放松一下")
    if meeting_pct < 5 and work_pct > 40:
        insights.append("你的会议参与度较低，适当参加会议可以提升协作效率和领导力")
    if chat_pct > 40:
        insights.append("你的社交非常活跃！但也要注意保持足够的工作专注时间")
    if not insights:
        insights.append("你的工作生活节奏均衡，继续保持！")

    # ── MBTI行为对比 ──
    profile_result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == agent_id)
    )
    profile = profile_result.scalar_one_or_none()
    mbti_comparison = {}

    if profile and profile.mbti:
        # 查询同MBTI类型Agent的平均行为
        same_mbti_result = await db.execute(
            select(AgentProfile.id).where(
                AgentProfile.mbti == profile.mbti,
                AgentProfile.id != agent_id,
            )
        )
        same_mbti_ids = [r.id for r in same_mbti_result.all()]

        if same_mbti_ids:
            avg_action_result = await db.execute(
                select(
                    AgentActionLog.action,
                    sa_func.count(AgentActionLog.id).label("count"),
                )
                .where(
                    AgentActionLog.agent_id.in_(same_mbti_ids),
                    AgentActionLog.created_at >= thirty_days_ago,
                )
                .group_by(AgentActionLog.action)
            )
            avg_actions = {row.action: row.count for row in avg_action_result.all()}
            avg_total = sum(avg_actions.values()) or 1

            mbti_comparison = {
                "my_mbti": profile.mbti,
                "sample_size": len(same_mbti_ids),
                "my_work_pct": work_pct,
                "avg_work_pct": round(avg_actions.get("work", 0) / avg_total * 100, 1),
                "my_chat_pct": chat_pct,
                "avg_chat_pct": round(avg_actions.get("chat", 0) / avg_total * 100, 1),
                "my_rest_pct": rest_pct,
                "avg_rest_pct": round(avg_actions.get("rest", 0) / avg_total * 100, 1),
            }

    return {
        "activity_heatmap": activity_heatmap,
        "action_distribution": action_distribution,
        "action_percentage": action_pct,
        "insights": insights,
        "mbti_comparison": mbti_comparison,
    }


async def get_career_prediction(db: AsyncSession, agent_id: int) -> dict:
    """
    基于当前数据预测晋升时间和职业轨迹。
    """
    from app.schemas.agent_social import CAREER_LEVELS

    profile_result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == agent_id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        return {}

    current_level = profile.career_level or 0
    current_xp = profile.xp or 0
    tasks_completed = profile.tasks_completed or 0

    # 计算近7天的平均每日XP增长
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_xp_result = await db.execute(
        select(sa_func.sum(AgentTask.xp_reward)).where(
            AgentTask.assignee_id == agent_id,
            AgentTask.status == "completed",
            AgentTask.completed_at >= week_ago,
        )
    )
    weekly_xp = recent_xp_result.scalar() or 0
    daily_xp_rate = weekly_xp / 7 if weekly_xp > 0 else 10  # 默认每日10XP

    recent_tasks_result = await db.execute(
        select(sa_func.count(AgentTask.id)).where(
            AgentTask.assignee_id == agent_id,
            AgentTask.status == "completed",
            AgentTask.completed_at >= week_ago,
        )
    )
    weekly_tasks = recent_tasks_result.scalar() or 0
    daily_task_rate = weekly_tasks / 7 if weekly_tasks > 0 else 0.5

    # 预测每个未来等级
    predictions = []
    cumulative_days = 0
    for level in range(current_level + 1, 7):
        req = CAREER_LEVELS.get(level, {})
        xp_needed = max(0, req.get("xp_required", 0) - current_xp)
        tasks_needed = max(0, req.get("tasks_required", 0) - tasks_completed)

        days_by_xp = xp_needed / daily_xp_rate if daily_xp_rate > 0 else 999
        days_by_tasks = tasks_needed / daily_task_rate if daily_task_rate > 0 else 999
        days_needed = max(days_by_xp, days_by_tasks)
        cumulative_days += days_needed

        predictions.append({
            "level": level,
            "title": req.get("title", "未知"),
            "days_needed": round(days_needed, 1),
            "cumulative_days": round(cumulative_days, 1),
            "xp_required": req.get("xp_required", 0),
            "tasks_required": req.get("tasks_required", 0),
        })

        # 模拟XP和任务增长
        current_xp += xp_needed
        tasks_completed += tasks_needed

    # 同级别排名
    rank_result = await db.execute(
        select(sa_func.count(AgentProfile.id)).where(
            AgentProfile.career_level == current_level,
            AgentProfile.xp > (profile.xp or 0),
        )
    )
    higher_count = rank_result.scalar() or 0

    total_same_level_result = await db.execute(
        select(sa_func.count(AgentProfile.id)).where(
            AgentProfile.career_level == current_level,
        )
    )
    total_same = total_same_level_result.scalar() or 1

    percentile = round((1 - higher_count / total_same) * 100, 1) if total_same > 0 else 50

    return {
        "current_level": current_level,
        "current_title": CAREER_LEVELS.get(current_level, {}).get("title", "未知"),
        "daily_xp_rate": round(daily_xp_rate, 1),
        "daily_task_rate": round(daily_task_rate, 2),
        "predictions": predictions,
        "percentile_rank": percentile,
    }
