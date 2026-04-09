"""
频道自动化引擎 - 每日公告、部门闲聊、用户消息回复
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

# 跟踪最后一次发布公告的日期，避免重复
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
    0: "实习生", 1: "初级员工", 2: "员工", 3: "高级员工",
    4: "经理", 5: "���监", 6: "CEO",
}

DEPT_FALLBACK_MESSAGES = {
    "engineering": [
        "今天的代码review完成了，大家有什么问题欢迎讨论",
        "刚跑完测试，通过率不错，继续保持！",
        "有人在用新框架遇到配置问题吗？",
        "提醒：周五前记得提交进度报告",
        "本地环境重启了一次，现在稳定了",
    ],
    "marketing": [
        "本周活动方案出来了，大家可以看看",
        "竞品分析报告整理好了，一会发群里",
        "用户反馈汇总完成，有几个有意思的点",
        "新的推广文案需要大家帮忙看看语气",
        "这周转化率比上周提升了不少",
    ],
    "finance": [
        "月度报表已更新，请各部门核对数据",
        "提醒大家报销单要在本月底前提交",
        "预算审批流程有调整，具体看文件",
        "Q季度数据汇总完毕，整体表现还行",
        "资金流水已对账，没有异常",
    ],
    "hr": [
        "新同事入职培训安排好了，欢迎大家关照",
        "绩效面谈本周开始，请各位配合",
        "团建活动投票结果出来了！",
        "招聘进展顺利，下周有新成员加入",
        "培训资料已更新，有空可以看看",
    ],
    "product": [
        "新版本需求文档已在共享文件夹，请大家review",
        "用户调研结果整理完了，发现几个核心痛点",
        "下个迭代的功能优先级排好了，来讨论一下",
        "原型图更新了，欢迎大家提意见",
        "本周用户访谈收获不少，稍后分享给大家",
    ],
    "operations": [
        "服务器本周监控正常，无告警",
        "部署流程优化了一版，减少了手动步骤",
        "数据备份已验证，一切正常",
        "本周SLA达标，继续保持",
        "新的运维文档整理好了，大家可以参考",
    ],
    "management": [
        "本周重点工作对齐完成，各部门按计划推进",
        "季度目标完成度看起来不错，继续加油",
        "跨部门协作事项请及时同步进展",
        "管理层会议纪要已发出，请查收",
        "各部门负责人记得本周五前提交周报",
    ],
}


async def _broadcast_channel_message(group_id: str, msg: AgentMessage, sender: AgentProfile):
    """通过WebSocket广播频道消息"""
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
    """生成并发布每日全公司公告"""
    global _last_announcement_date
    today = datetime.now(timezone.utc).date()
    if _last_announcement_date == today:
        return  # 今天已经发过了

    async with AsyncSessionLocal() as db:
        try:
            # 优先找管理层NPC作为发布人
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
            career_title = CAREER_TITLE_MAP.get(announcer.career_level or 0, "员工")

            try:
                llm_result = await call_llm_json(
                    DAILY_ANNOUNCEMENT_PROMPT.format(
                        date=today.strftime("%Y年%m月%d日"),
                        announcer_name=announcer.nickname,
                        announcer_title=career_title,
                    ),
                    system_prompt="你是虚拟公司公告生成助手，请生成简短自然的公告内容。",
                    cache_prefix="daily_announcement",
                    use_cache=False,
                )
                if isinstance(llm_result, dict) and "announcement" in llm_result:
                    content = llm_result["announcement"]
                else:
                    content = f"【{today.strftime('%m月%d日')}】各位同仁好，今日公司运营正常，感谢大家的努力！——{announcer.nickname}"
            except Exception:
                content = f"【{today.strftime('%m月%d日')}】大家好，今日工作顺利推进，继续加油！——{announcer.nickname}"

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
    """触发部门频道中的AI角色发一条日常消息"""
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

            # 获取最近5条消息作为上下文
            recent_result = await db.execute(
                select(AgentMessage)
                .where(AgentMessage.group_id == group_id)
                .order_by(AgentMessage.created_at.desc())
                .limit(5)
            )
            recent_msgs = list(recent_result.scalars().all())
            recent_msgs.reverse()
            history = "\n".join(f"{m.content}" for m in recent_msgs) if recent_msgs else "（频道暂无消息）"

            career_title = CAREER_TITLE_MAP.get(npc.career_level or 0, "员工")

            try:
                llm_result = await call_llm_json(
                    CHANNEL_CHAT_PROMPT.format(
                        nickname=npc.nickname,
                        mbti=npc.mbti or "ISTJ",
                        career_title=career_title,
                        department=department,
                        recent_history=history,
                    ),
                    system_prompt="你是虚拟公司员工，在部门频道发日常消息。",
                    cache_prefix="dept_chat",
                    use_cache=False,
                )
                if isinstance(llm_result, dict) and "message" in llm_result:
                    content = llm_result["message"]
                else:
                    content = random.choice(DEPT_FALLBACK_MESSAGES.get(department, ["大家好！"]))
            except Exception:
                content = random.choice(DEPT_FALLBACK_MESSAGES.get(department, ["大家好！"]))

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
    """对用户在频道中的消息生成NPC回复（带自然延迟）"""
    await asyncio.sleep(random.uniform(6, 18))  # 自然的回复延迟

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

            # 获取发言用户名字
            user_result = await db.execute(
                select(AgentProfile).where(AgentProfile.id == user_sender_id)
            )
            user_profile = user_result.scalar_one_or_none()
            user_name = user_profile.nickname if user_profile else "同事"

            career_title = CAREER_TITLE_MAP.get(npc.career_level or 0, "员工")

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
                    system_prompt="你是虚拟公司员工，在部门频道回复同事消息。",
                    cache_prefix="channel_reply",
                    use_cache=False,
                )
                if isinstance(llm_result, dict) and "reply" in llm_result:
                    content = llm_result["reply"]
                else:
                    content = f"好的，{user_name}，了解了！"
            except Exception:
                content = f"收到，{user_name}！👍"

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
