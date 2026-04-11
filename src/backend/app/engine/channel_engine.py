"""
Channels automation engine - daily Announcement, Department chat, user information reply
"""
import asyncio
import logging
import random
from datetime import datetime, timezone, date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.agent_profile import AgentProfile
from app.models.agent_message import AgentMessage
from app.prompts.agent_prompt import (
    DAILY_ANNOUNCEMENT_PROMPT,
    CHANNEL_CHAT_PROMPT,
    CHANNEL_REPLY_PROMPT,
)
from app.utils.llm import call_llm_json

logger = logging.getLogger(__name__)

# Track the date of the last Announcement，avoid duplication
_last_announcement_date: date | None = None

DEPT_CHANNEL_MAP = {
    "engineering":  "dept_engineering",
    "marketing":    "dept_marketing",
    "finance":      "dept_finance",
    "hr":           "dept_hr",
    "product":      "dept_product",
    "operations":   "dept_operations",
    "management":   "dept_management",
}

CAREER_TITLE_MAP = {
    0: "Intern", 1: "Junior Staff", 2: "Staff", 3: "Senior Staff",
    4: "Manager", 5: "���supervise", 6: "CEO",
}

DEPT_FALLBACK_MESSAGES = {
    "engineering": [
        "Today's code review is completed，Do you have any questions? Welcome to discuss.",
        "Just finished running Tests，Good pass rate，keep it up！",
        "Has anyone encountered configuration issues with the new framework?？",
        "remind：Remember to submit your progress report before Friday",
        "The local environment was restarted once，Stable now",
    ],
    "marketing": [
        "This week the Activity plan is out，You can take a look",
        "Competitive product analysis reports have been sorted out，Will post in group soon",
        "Summary of user feedback completed，There are a few interesting points",
        "The new promotion copy needs your help to check the tone.",
        "The conversion rate this week has improved a lot compared to last week",
    ],
    "finance": [
        "Monthly report has been updated，Please check the data with each Department",
        "Remind everyone that reimbursement forms must be submitted before the end of this month",
        "The budget approval process has been adjusted，See the document for details",
        "Q quarter data summary completed，Overall performance is okay",
        "Fund flow has been reconciled，No exception",
    ],
    "hr": [
        "Training for new Colleague has been arranged，Welcome, take care of everyone",
        "Performance interviews start this week，Please cooperate",
        "Team BuildingActivity voting results are out！",
        "Recruitment is going well，New members will join next week",
        "Training information has been updated，You can take a look when you have time",
    ],
    "product": [
        "The new version of the requirements document is already in the shared folder，Please review",
        "User research results have been compiled，Discovered several core pain points",
        "The Function priorities for the next iteration have been arranged.，Let's discuss",
        "The prototype diagram has been updated，Welcome everyone's comments",
        "I learned a lot from the user interviews this week，Share with everyone later",
    ],
    "operations": [
        "Server monitoring is normal this week，No alarm",
        "The deployment process has been optimized.，Reduced manual steps",
        "data backup verified，everything is fine",
        "SLA met this week，keep it up",
        "The new operation and maintenance documents have been sorted out，You can refer to",
    ],
    "management": [
        "This week's key work alignment is completed，Each Department is progressing as planned",
        "Quarterly target achievement looks good，keep pushing",
        "Please synchronize progress on cross-Department collaboration matters in a timely manner",
        "Management FloorMeeting minutes have been sent，Please check",
        "Heads of each Department remember to submit weekly reports before this Friday",
    ],
}


async def _broadcast_channel_message(group_id: str, msg: AgentMessage, sender: AgentProfile):
    """Broadcast Channels messages via WebSocket"""
    try:
        from app.routers.agent_ws import manager
        await manager.broadcast({
            "type": "channel_message",
            "group_id": group_id,
            "message": {
                "id": msg.id,
                "sender_id": sender.id,
                "sender_nickname": sender.nickname,
                "sender_avatar": sender.avatar_key or "",
                "content": msg.content,
                "msg_type": msg.msg_type,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            },
        })
    except Exception as e:
        logger.debug("WS broadcast channel_message failed: %s", e)


async def post_daily_announcement():
    """Generate and publish daily company-wide Announcements"""
    global _last_announcement_date
    today = datetime.now(timezone.utc).date()
    if _last_announcement_date == today:
        return  # Already sent it today

    async with AsyncSessionLocal() as db:
        try:
            # Prioritize finding Management FloorNPC as the publisher
            result = await db.execute(
                select(AgentProfile).where(
                    AgentProfile.ai_enabled == True,
                    AgentProfile.career_level >= 4,
                )
            )
            managers = result.scalars().all()

            if not managers:
                result = await db.execute(
                    select(AgentProfile).where(AgentProfile.ai_enabled == True).limit(3)
                )
                managers = result.scalars().all()

            if not managers:
                return

            announcer = random.choice(managers)
            career_title = CAREER_TITLE_MAP.get(announcer.career_level or 0, "Staff")

            try:
                llm_result = await call_llm_json(
                    DAILY_ANNOUNCEMENT_PROMPT.format(
                        date=today.strftime("%Y%mDay of month %d"),
                        announcer_name=announcer.nickname,
                        announcer_title=career_title,
                    ),
                    system_prompt="you are virtual companyAnnouncement generation assistant，Please generate short and natural Announcement content。",
                    cache_prefix="daily_announcement",
                    use_cache=False,
                )
                if isinstance(llm_result, dict) and "announcement" in llm_result:
                    content = llm_result["announcement"]
                else:
                    content = f"【{today.strftime('%mDay of month %d')}】Hello colleagues，The company is operating normally today，thank you all for your efforts！——{announcer.nickname}"
            except Exception:
                content = f"【{today.strftime('%mDay of month %d')}】Hello everyone，Work progresses smoothly today，keep pushing！——{announcer.nickname}"

            msg = AgentMessage(
                sender_id=announcer.id,
                receiver_id=None,
                content=content,
                msg_type="ai_generated",
                group_id="announcement",
            )
            db.add(msg)
            await db.commit()
            await db.refresh(msg)

            await _broadcast_channel_message("announcement", msg, announcer)
            _last_announcement_date = today
            logger.info("Daily announcement posted by %s", announcer.nickname)

        except Exception as e:
            logger.error("Failed to post daily announcement: %s", e)


async def post_department_chatter(department: str):
    """Trigger the AI character in DepartmentChannels to send a message msgs daily information"""
    group_id = DEPT_CHANNEL_MAP.get(department)
    if not group_id:
        return

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(AgentProfile).where(
                    AgentProfile.department == department,
                    AgentProfile.ai_enabled == True,
                )
            )
            npcs = result.scalars().all()
            if not npcs:
                return

            npc = random.choice(npcs)

            # Get the last 5 msgsinformation as context
            recent_result = await db.execute(
                select(AgentMessage)
                .where(AgentMessage.group_id == group_id)
                .order_by(AgentMessage.created_at.desc())
                .limit(5)
            )
            recent_msgs = list(recent_result.scalars().all())
            recent_msgs.reverse()
            history = "\n".join(f"{m.content}" for m in recent_msgs) if recent_msgs else "（ChannelsNo messages yet）"

            career_title = CAREER_TITLE_MAP.get(npc.career_level or 0, "Staff")

            try:
                llm_result = await call_llm_json(
                    CHANNEL_CHAT_PROMPT.format(
                        nickname=npc.nickname,
                        mbti=npc.mbti or "ISTJ",
                        career_title=career_title,
                        department=department,
                        recent_history=history,
                    ),
                    system_prompt="you are virtual companyStaff，Send daily messages on DepartmentChannels。",
                    cache_prefix="dept_chat",
                    use_cache=False,
                )
                if isinstance(llm_result, dict) and "message" in llm_result:
                    content = llm_result["message"]
                else:
                    content = random.choice(DEPT_FALLBACK_MESSAGES.get(department, ["Hello everyone!"]))
            except Exception:
                content = random.choice(DEPT_FALLBACK_MESSAGES.get(department, ["Hello everyone!"]))

            msg = AgentMessage(
                sender_id=npc.id,
                receiver_id=None,
                content=content,
                msg_type="ai_generated",
                group_id=group_id,
            )
            db.add(msg)
            await db.commit()
            await db.refresh(msg)

            await _broadcast_channel_message(group_id, msg, npc)
            logger.info("Dept chatter: %s posted in %s", npc.nickname, group_id)

        except Exception as e:
            logger.error("Failed to post dept chatter for %s: %s", department, e)


async def post_channel_reply(group_id: str, user_sender_id: int, user_message: str, department: str):
    """Generate NPC replies to user messages in Channels（with natural delay）"""
    await asyncio.sleep(random.uniform(6, 18))  # natural reply delay

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(AgentProfile).where(
                    AgentProfile.department == department,
                    AgentProfile.ai_enabled == True,
                    AgentProfile.id != user_sender_id,
                )
            )
            npcs = result.scalars().all()
            if not npcs:
                return

            npc = random.choice(npcs)

            # Get the speaking username word
            user_result = await db.execute(
                select(AgentProfile).where(AgentProfile.id == user_sender_id)
            )
            user_profile = user_result.scalar_one_or_none()
            user_name = user_profile.nickname if user_profile else "Colleague"

            career_title = CAREER_TITLE_MAP.get(npc.career_level or 0, "Staff")

            try:
                llm_result = await call_llm_json(
                    CHANNEL_REPLY_PROMPT.format(
                        nickname=npc.nickname,
                        mbti=npc.mbti or "ISTJ",
                        career_title=career_title,
                        department=department,
                        user_name=user_name,
                        user_message=user_message,
                    ),
                    system_prompt="you are virtual companyStaff，Reply to Colleague message in DepartmentChannels。",
                    cache_prefix="channel_reply",
                    use_cache=False,
                )
                if isinstance(llm_result, dict) and "reply" in llm_result:
                    content = llm_result["reply"]
                else:
                    content = f"Got it, {user_name}，Understood！"
            except Exception:
                content = f"Received, {user_name}！👍"

            msg = AgentMessage(
                sender_id=npc.id,
                receiver_id=None,
                content=content,
                msg_type="ai_generated",
                group_id=group_id,
            )
            db.add(msg)
            await db.commit()
            await db.refresh(msg)

            await _broadcast_channel_message(group_id, msg, npc)

        except Exception as e:
            logger.error("Failed to post channel reply: %s", e)
