"""
薪资引擎
"""
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func, String, cast

from app.models.agent_profile import AgentProfile
from app.models.agent_salary_log import AgentSalaryLog
from app.models.agent_task import AgentTask
from app.models.coin_wallet import CoinWallet, CoinTransaction


# 薪资表：按career_level
SALARY_TABLE = {
    0: 50,    # 实习生
    1: 100,   # 初级员工
    2: 200,   # 中级员工
    3: 350,   # 高级员工
    4: 500,   # 经理
    5: 800,   # 总监
    6: 1200,  # CEO
}


def calculate_daily_salary(agent: AgentProfile, expired_count: int = 0) -> dict:
    """
    计算日薪 = 基础薪资 + 绩效加成 - 过期任务惩罚

    绩效加成公式：base * min(0.20, max(0, (completed - expired) * 0.002))
    如果本月 expired > completed，额外惩罚：salary * 0.9
    """
    base = SALARY_TABLE.get(agent.career_level, 50)

    # 绩效：考虑过期任务的影响
    completed = agent.tasks_completed or 0
    effective_tasks = max(0, completed - expired_count)
    perf_rate = min(0.20, max(0, effective_tasks * 0.002))
    perf_bonus = int(base * perf_rate)

    total = base + perf_bonus

    # 如果过期任务数量超过完成数量，应用惩罚系数
    penalty_applied = False
    if expired_count > completed:
        total = int(total * 0.9)
        penalty_applied = True

    return {
        "base_salary": base,
        "performance_bonus": perf_bonus,
        "total": total,
        "performance_rate": round(perf_rate * 100, 1),
        "expired_count": expired_count,
        "penalty_applied": penalty_applied,
    }


async def _get_monthly_expired_count(db: AsyncSession, agent_id: int) -> int:
    """获取Agent本月过期任务数量"""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(sa_func.count(AgentTask.id)).where(
            AgentTask.assignee_id == agent_id,
            AgentTask.status == "expired",
            AgentTask.created_at >= month_start,
        )
    )
    return result.scalar() or 0


async def distribute_salaries(db: AsyncSession) -> dict:
    """
    遍历所有Agent发放日薪，写入AgentSalaryLog + CoinWallet
    返回统计数据
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    result = await db.execute(select(AgentProfile))
    agents = result.scalars().all()

    paid_count = 0
    total_paid = 0

    for agent in agents:
        # 检查今天是否已发放
        existing = await db.execute(
            select(AgentSalaryLog).where(
                AgentSalaryLog.agent_id == agent.id,
                cast(AgentSalaryLog.paid_at, String).like(f"{today_str}%"),
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            continue

        # 获取本月过期任务数
        expired_count = await _get_monthly_expired_count(db, agent.id)

        salary_info = calculate_daily_salary(agent, expired_count=expired_count)
        amount = salary_info["total"]

        # 构造描述
        desc = f"日薪: 基础{salary_info['base_salary']} + 绩效{salary_info['performance_bonus']}"
        if salary_info["penalty_applied"]:
            desc += " (过期任务惩罚-10%)"

        # 记录薪资日志
        log = AgentSalaryLog(
            agent_id=agent.id,
            amount=amount,
            salary_type="daily",
            description=desc,
        )
        db.add(log)

        # 发放到钱包
        wallet_result = await db.execute(
            select(CoinWallet).where(CoinWallet.user_id == agent.user_id)
        )
        wallet = wallet_result.scalar_one_or_none()
        if wallet:
            wallet.balance += amount
            tx = CoinTransaction(
                user_id=agent.user_id,
                amount=amount,
                tx_type="salary",
                description=f"日薪发放 (Lv.{agent.career_level})",
            )
            db.add(tx)

        paid_count += 1
        total_paid += amount

    await db.flush()
    return {
        "paid_count": paid_count,
        "total_paid": total_paid,
        "date": today_str,
    }
