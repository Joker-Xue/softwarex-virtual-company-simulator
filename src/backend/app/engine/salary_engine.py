"""
Compensationengine
"""
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func, String, cast

from app.models.agent_profile import AgentProfile
from app.models.agent_salary_log import AgentSalaryLog
from app.models.agent_task import AgentTask
from app.models.coin_wallet import CoinWallet, CoinTransaction


# Compensation table：by career_level
SALARY_TABLE = {
    0: 50,    # Intern
    1: 100,   # Junior Staff
    2: 200,   # Mid-level Staff
    3: 350,   # Senior Staff
    4: 500,   # Manager
    5: 800,   # Director
    6: 1200,  # CEO
}


def calculate_daily_salary(agent: AgentProfile, expired_count: int = 0) -> dict:
    """
    Calculate Daily Pay = Base Salary + Performance Bonus - Expired Task Penalty

    Performance Bonusformula：base * min(0.20, max(0, (completed - expired) * 0.002))
    If this month expired > completed，additional punishment：salary * 0.9
    """
    base = SALARY_TABLE.get(agent.career_level, 50)

    # performance：Consider the impact of expired tasks
    completed = agent.tasks_completed or 0
    effective_tasks = max(0, completed - expired_count)
    perf_rate = min(0.20, max(0, effective_tasks * 0.002))
    perf_bonus = int(base * perf_rate)

    total = base + perf_bonus

    # If the number of overdue tasks exceeds the number of completed tasks，Apply penalty coefficient
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
    """Get the number of expired tasks of Agent this month"""
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
    Traverse all Agents and issue Daily Pay，Write to AgentSalaryLog + CoinWallet
    Backstatistics
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    result = await db.execute(select(AgentProfile))
    agents = result.scalars().all()

    paid_count = 0
    total_paid = 0

    for agent in agents:
        # Check if it has been issued today
        existing = await db.execute(
            select(AgentSalaryLog).where(
                AgentSalaryLog.agent_id == agent.id,
                cast(AgentSalaryLog.paid_at, String).like(f"{today_str}%"),
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            continue

        # Get the number of expired tasks this month
        expired_count = await _get_monthly_expired_count(db, agent.id)

        salary_info = calculate_daily_salary(agent, expired_count=expired_count)
        amount = salary_info["total"]

        # Construction description
        desc = f"Daily Pay: Base{salary_info['base_salary']} + performance{salary_info['performance_bonus']}"
        if salary_info["penalty_applied"]:
            desc += " (Expired Task Penalty -10%)"

        # Record Compensation log
        log = AgentSalaryLog(
            agent_id=agent.id,
            amount=amount,
            salary_type="daily",
            description=desc,
        )
        db.add(log)

        # Send to wallet
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
                description=f"Daily Pay issuance (Lv.{agent.career_level})",
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
