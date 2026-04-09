"""
任务生成器 — 个性化任务生成（混合模式：LLM + 确定性回退）
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
        {"title": "重构API接口", "description": "优化现有API的代码结构", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "工程部办公区", "contact": "刘工"},
        {"title": "编写单元测试", "description": "为核心模块补充测试用例", "difficulty": 2, "xp_reward": 30, "tag": "technical", "location": "工程部办公区", "contact": "马弟"},
        {"title": "修复线上Bug", "description": "排查并修复用户反馈的问题", "difficulty": 3, "xp_reward": 35, "tag": "technical", "location": "工程部办公区", "contact": "张经理"},
        {"title": "技术方案评审", "description": "评审新功能的技术方案", "difficulty": 2, "xp_reward": 25, "tag": "creative", "location": "会议室A", "contact": "王总监"},
        {"title": "性能优化", "description": "优化系统响应速度", "difficulty": 4, "xp_reward": 50, "tag": "technical", "location": "工程部办公区", "contact": "刘工"},
        {"title": "代码Review", "description": "审查同事提交的代码PR", "difficulty": 2, "xp_reward": 25, "tag": "technical", "location": "工程部办公区", "contact": "马弟"},
        {"title": "编写技术文档", "description": "为新模块撰写技术文档", "difficulty": 2, "xp_reward": 20, "tag": "creative", "location": "工程部办公区", "contact": "张经理"},
        {"title": "搭建CI/CD���水线", "description": "配置自动化构建和部署", "difficulty": 4, "xp_reward": 55, "tag": "technical", "location": "工程部办公区", "contact": "刘工"},
        {"title": "数据库索引优化", "description": "分析慢查询并添加索引", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "工程部办公区", "contact": "刘工"},
        {"title": "安全漏洞排查", "description": "检查系统潜在安全风险", "difficulty": 4, "xp_reward": 50, "tag": "technical", "location": "工程部办公区", "contact": "王总监"},
        {"title": "微服务拆分设计", "description": "设计单体拆分方案", "difficulty": 5, "xp_reward": 65, "tag": "creative", "location": "会议室A", "contact": "陈总"},
        {"title": "技术分享准备", "description": "准备周五技术分享材料", "difficulty": 2, "xp_reward": 25, "tag": "social", "location": "会议室A", "contact": "张经理"},
        {"title": "新人代码指导", "description": "帮助新同事熟悉代码库", "difficulty": 2, "xp_reward": 30, "tag": "social", "location": "工程部办公区", "contact": "马弟"},
        {"title": "监控告警配置", "description": "配置服务监控和告警规则", "difficulty": 3, "xp_reward": 35, "tag": "technical", "location": "工程部办公区", "contact": "刘工"},
        {"title": "接口联调", "description": "与前端团队进行接口联调", "difficulty": 2, "xp_reward": 30, "tag": "social", "location": "会议室A", "contact": "张经理"},
    ],
    "marketing": [
        {"title": "撰写推广文案", "description": "为新功能撰写推广文案", "difficulty": 2, "xp_reward": 25, "tag": "creative", "location": "市场部办公区", "contact": "周姐"},
        {"title": "分析用户数据", "description": "分析本周用户行为数据", "difficulty": 3, "xp_reward": 35, "tag": "technical", "location": "市场部办公区", "contact": "李总监"},
        {"title": "策划活动方案", "description": "策划下月线上推广活动", "difficulty": 3, "xp_reward": 40, "tag": "creative", "location": "会议室A", "contact": "李总监"},
        {"title": "竞品分析报告", "description": "调研竞品最新动态", "difficulty": 2, "xp_reward": 30, "tag": "technical", "location": "市场部办公区", "contact": "郑姐"},
        {"title": "社交媒体运营", "description": "更新社交媒体内容", "difficulty": 1, "xp_reward": 15, "tag": "creative", "location": "市场部办公区", "contact": "周姐"},
        {"title": "用户访谈整理", "description": "整理用户访谈记录和洞察", "difficulty": 2, "xp_reward": 25, "tag": "social", "location": "咖啡厅", "contact": "郑姐"},
        {"title": "品牌VI设计评审", "description": "评审品牌视觉设计���", "difficulty": 3, "xp_reward": 35, "tag": "creative", "location": "会议室A", "contact": "李总监"},
        {"title": "渠道投放分析", "description": "分析各渠道ROI数据", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "市场部办公区", "contact": "周姐"},
        {"title": "制作宣传视频", "description": "拍摄并剪辑产品宣传短视频", "difficulty": 4, "xp_reward": 50, "tag": "creative", "location": "市场部办公区", "contact": "郑姐"},
        {"title": "SEO优化方案", "description": "制定搜索引擎优化策略", "difficulty": 3, "xp_reward": 35, "tag": "technical", "location": "市场部办公区", "contact": "周姐"},
        {"title": "KOL合作对接", "description": "联系KOL洽谈合作", "difficulty": 3, "xp_reward": 40, "tag": "social", "location": "咖啡厅", "contact": "李总监"},
        {"title": "市场调研报告", "description": "撰写行业市场调研报告", "difficulty": 4, "xp_reward": 50, "tag": "technical", "location": "市场部办公区", "contact": "李总监"},
        {"title": "新闻稿撰写", "description": "撰写产品发布新闻稿", "difficulty": 2, "xp_reward": 25, "tag": "creative", "location": "市场部办公区", "contact": "周姐"},
        {"title": "用户增长策略", "description": "制定下季度用户增长方案", "difficulty": 4, "xp_reward": 55, "tag": "creative", "location": "会议室A", "contact": "李总监"},
        {"title": "品牌合作洽谈", "description": "与合作品牌商务沟通", "difficulty": 3, "xp_reward": 35, "tag": "social", "location": "咖啡厅", "contact": "郑姐"},
    ],
    "finance": [
        {"title": "月度财务报表", "description": "整理本月收支数据", "difficulty": 2, "xp_reward": 30, "tag": "technical", "location": "财务部办公区", "contact": "吴哥"},
        {"title": "预算审批", "description": "审核部门提交的预算申请", "difficulty": 3, "xp_reward": 35, "tag": "technical", "location": "会议室A", "contact": "陈总"},
        {"title": "成本分析", "description": "分析各部门运营成本", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "财务部办公区", "contact": "吴哥"},
        {"title": "发票处理", "description": "处理本周的发票和报销", "difficulty": 1, "xp_reward": 15, "tag": "technical", "location": "财务部办公区", "contact": "林弟"},
        {"title": "税务合规检查", "description": "检查税务申报材料", "difficulty": 4, "xp_reward": 50, "tag": "technical", "location": "财务部办公区", "contact": "吴哥"},
        {"title": "现金流预测", "description": "编制下月现金流预测表", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "财务部办公区", "contact": "吴哥"},
        {"title": "投资回报分析", "description": "分析各项目投资回报率", "difficulty": 4, "xp_reward": 50, "tag": "technical", "location": "财务部办公区", "contact": "林弟"},
        {"title": "审计准备", "description": "准备季度审计所需材料", "difficulty": 3, "xp_reward": 35, "tag": "technical", "location": "会议室A", "contact": "王总监"},
        {"title": "薪酬核算", "description": "核算本月员工薪酬数据", "difficulty": 2, "xp_reward": 30, "tag": "technical", "location": "财务部办公区", "contact": "林弟"},
        {"title": "风险评估报告", "description": "编写财务风险评估报告", "difficulty": 4, "xp_reward": 55, "tag": "creative", "location": "财务部办公区", "contact": "吴哥"},
        {"title": "资产盘点", "description": "组织公司固定资产盘点", "difficulty": 2, "xp_reward": 25, "tag": "management", "location": "财务部办公区", "contact": "林弟"},
        {"title": "财务培训", "description": "为各部门做报销制度培训", "difficulty": 2, "xp_reward": 25, "tag": "social", "location": "会议室A", "contact": "赵经理"},
        {"title": "合同审核", "description": "审核供应商合同条款", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "财务部办公区", "contact": "吴哥"},
        {"title": "财务系统优化", "description": "优化财务管理系统流程", "difficulty": 3, "xp_reward": 35, "tag": "creative", "location": "财务部办公区", "contact": "林弟"},
        {"title": "年度预算编制", "description": "协助编制年度财务预算", "difficulty": 5, "xp_reward": 65, "tag": "technical", "location": "会议室A", "contact": "陈总"},
    ],
    "hr": [
        {"title": "筛选简历", "description": "筛选本周收到的应聘简历", "difficulty": 1, "xp_reward": 15, "tag": "technical", "location": "HR部办公区", "contact": "黄妹"},
        {"title": "组织团建活动", "description": "策划本月团建方案", "difficulty": 2, "xp_reward": 30, "tag": "creative", "location": "咖啡厅", "contact": "赵经理"},
        {"title": "员工满意度调查", "description": "设计并发放满意度问卷", "difficulty": 2, "xp_reward": 25, "tag": "creative", "location": "HR部办公区", "contact": "黄妹"},
        {"title": "培训计划制定", "description": "制定新员工培训计划", "difficulty": 3, "xp_reward": 35, "tag": "creative", "location": "会议室A", "contact": "赵经理"},
        {"title": "绩效考核", "description": "整理本季度绩效考核数据", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "HR部办公区", "contact": "赵经理"},
        {"title": "面试候选人", "description": "面试3位候选人", "difficulty": 3, "xp_reward": 35, "tag": "social", "location": "会议室A", "contact": "赵经理"},
        {"title": "员工关怀方案", "description": "制定员工心理关怀计划", "difficulty": 2, "xp_reward": 25, "tag": "creative", "location": "HR部办公区", "contact": "黄妹"},
        {"title": "薪酬调研", "description": "调研行业薪酬水平", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "HR部办公区", "contact": "赵经理"},
        {"title": "入职引导", "description": "引导新员工入职流程", "difficulty": 1, "xp_reward": 20, "tag": "social", "location": "大厅", "contact": "黄妹"},
        {"title": "考勤数据整理", "description": "汇总本月考勤异常数据", "difficulty": 1, "xp_reward": 15, "tag": "technical", "location": "HR部办公区", "contact": "黄妹"},
        {"title": "企业文化建设", "description": "策划企业文化活动", "difficulty": 3, "xp_reward": 40, "tag": "creative", "location": "咖啡厅", "contact": "赵经理"},
        {"title": "劳动合同管理", "description": "更新到期劳动合同", "difficulty": 2, "xp_reward": 25, "tag": "technical", "location": "HR部办公区", "contact": "黄妹"},
        {"title": "离职面谈", "description": "与离职员工进行面谈", "difficulty": 2, "xp_reward": 30, "tag": "social", "location": "会议室A", "contact": "赵经理"},
        {"title": "人才梯队规划", "description": "制定关键岗位人才梯队", "difficulty": 4, "xp_reward": 55, "tag": "management", "location": "会议室A", "contact": "陈总"},
        {"title": "员工手册更新", "description": "更新公司员工手册内容", "difficulty": 2, "xp_reward": 25, "tag": "creative", "location": "HR部办公区", "contact": "黄妹"},
    ],
    "product": [
        {"title": "需求评审会", "description": "主持本周需求评审，对齐产品方向", "difficulty": 3, "xp_reward": 35, "tag": "creative", "location": "会议室A", "contact": "孙经理"},
        {"title": "编写PRD文档", "description": "撰写新功能产品需求文档", "difficulty": 3, "xp_reward": 40, "tag": "creative", "location": "产品部办公区", "contact": "孙经理"},
        {"title": "用户体验调研", "description": "设计用户体验问卷并收集反馈", "difficulty": 2, "xp_reward": 30, "tag": "technical", "location": "产品部办公区", "contact": "钱工"},
        {"title": "原型设计迭代", "description": "基于反馈更新产品原型", "difficulty": 2, "xp_reward": 25, "tag": "creative", "location": "产品部办公区", "contact": "钱工"},
        {"title": "竞品功能拆解", "description": "拆解竞品核心功能逻辑", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "产品部办公区", "contact": "孙经理"},
        {"title": "产品数据分析", "description": "分析关键业务指标和用户漏斗", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "产品部办公区", "contact": "孙经理"},
        {"title": "AB测试方案", "description": "设计功能灰度发布的AB测试方案", "difficulty": 4, "xp_reward": 50, "tag": "technical", "location": "会议室A", "contact": "孙经理"},
        {"title": "跨部门需求对齐", "description": "与技术、运营对齐迭代优先级", "difficulty": 2, "xp_reward": 30, "tag": "social", "location": "会议室A", "contact": "钱工"},
        {"title": "用户故事地图", "description": "绘制核心功能用户旅程地图", "difficulty": 3, "xp_reward": 35, "tag": "creative", "location": "产品部办公区", "contact": "孙经理"},
        {"title": "版本迭代复盘", "description": "组织上线版本迭代复盘会", "difficulty": 2, "xp_reward": 25, "tag": "social", "location": "会议室A", "contact": "孙经理"},
        {"title": "OKR制定", "description": "制定产品部本季度OKR目标", "difficulty": 4, "xp_reward": 55, "tag": "management", "location": "总监办公室", "contact": "陈总"},
        {"title": "新功能内测", "description": "组织内部测试新功能并收集Bug", "difficulty": 2, "xp_reward": 30, "tag": "technical", "location": "产品部办公区", "contact": "钱工"},
        {"title": "产品路线图更新", "description": "更新产品年度规划路线图", "difficulty": 4, "xp_reward": 50, "tag": "creative", "location": "产品部办公区", "contact": "孙经理"},
        {"title": "商业模式分析", "description": "分析产品商业化路径和盈利模式", "difficulty": 5, "xp_reward": 65, "tag": "creative", "location": "CEO办公室", "contact": "陈总"},
        {"title": "用户增长专项", "description": "制定核心功能用户增长策略", "difficulty": 4, "xp_reward": 50, "tag": "creative", "location": "会议室A", "contact": "孙经理"},
    ],
    "operations": [
        {"title": "日活数据监控", "description": "统计分析本日用户活跃数据", "difficulty": 1, "xp_reward": 20, "tag": "technical", "location": "运营部办公区", "contact": "韩妹"},
        {"title": "活动策划执行", "description": "策划并执行本周运营活动", "difficulty": 3, "xp_reward": 40, "tag": "creative", "location": "运营部办公区", "contact": "吕哥"},
        {"title": "内容选题会", "description": "确定本周内容发布选题", "difficulty": 2, "xp_reward": 25, "tag": "creative", "location": "会议室A", "contact": "吕哥"},
        {"title": "用户分层运营", "description": "制定不同用户群体的差异化运营策略", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "运营部办公区", "contact": "吕哥"},
        {"title": "推送文案撰写", "description": "撰写App推送和短信通知文案", "difficulty": 1, "xp_reward": 15, "tag": "creative", "location": "运营部办公区", "contact": "韩妹"},
        {"title": "社群维护", "description": "维护用户社群，解答用户问题", "difficulty": 1, "xp_reward": 20, "tag": "social", "location": "咖啡厅", "contact": "韩妹"},
        {"title": "运营数据周报", "description": "汇总本周核心运营指标周报", "difficulty": 2, "xp_reward": 30, "tag": "technical", "location": "运营部办公区", "contact": "吕哥"},
        {"title": "用户留存分析", "description": "分析用户7日/30日留存曲线", "difficulty": 3, "xp_reward": 40, "tag": "technical", "location": "运营部办公区", "contact": "吕哥"},
        {"title": "活动效果复盘", "description": "复盘上次活动转化效果", "difficulty": 2, "xp_reward": 30, "tag": "social", "location": "会议室A", "contact": "吕哥"},
        {"title": "竞品运营拆解", "description": "拆解竞品的运营策略和活动玩法", "difficulty": 3, "xp_reward": 35, "tag": "technical", "location": "运营部办公区", "contact": "吕哥"},
        {"title": "KPI目标拆解", "description": "将季度运营KPI分解到日/周维度", "difficulty": 3, "xp_reward": 40, "tag": "management", "location": "总监办公室", "contact": "陈总"},
        {"title": "渠道投放优化", "description": "优化各投放渠道出价策略", "difficulty": 4, "xp_reward": 50, "tag": "technical", "location": "运营部办公区", "contact": "吕哥"},
        {"title": "会员体系设计", "description": "设计用户会员等级和权益体系", "difficulty": 4, "xp_reward": 55, "tag": "creative", "location": "会议室A", "contact": "孙经理"},
        {"title": "跨部门协作", "description": "协调产品和技术推进运营需求", "difficulty": 2, "xp_reward": 30, "tag": "social", "location": "咖啡厅", "contact": "吕哥"},
        {"title": "增长实验设计", "description": "设计并上线增长实验方案", "difficulty": 4, "xp_reward": 55, "tag": "creative", "location": "运营部办公区", "contact": "吕哥"},
    ],
    "management": [
        {"title": "月度经营复盘", "description": "主持月度公司经营数据复盘", "difficulty": 4, "xp_reward": 60, "tag": "management", "location": "CEO办公室", "contact": "陈总"},
        {"title": "战略规划讨论", "description": "与各部门总监讨论季度战略方向", "difficulty": 5, "xp_reward": 70, "tag": "management", "location": "会议室A", "contact": "陈总"},
        {"title": "投资人汇报准备", "description": "准备投资人季度数据汇报材料", "difficulty": 4, "xp_reward": 60, "tag": "creative", "location": "CEO办公室", "contact": "陈总"},
        {"title": "部门绩效评估", "description": "评估各部门季度目标完成情况", "difficulty": 3, "xp_reward": 45, "tag": "management", "location": "总监办公室", "contact": "王总监"},
        {"title": "高管周会主持", "description": "主持每周高管对齐会议", "difficulty": 3, "xp_reward": 40, "tag": "social", "location": "会议室A", "contact": "陈总"},
        {"title": "人才晋升评审", "description": "组织高级别人才晋升评审会", "difficulty": 3, "xp_reward": 45, "tag": "management", "location": "总监办公室", "contact": "王总监"},
        {"title": "合作方商务洽谈", "description": "与重要合作方进行商务谈判", "difficulty": 4, "xp_reward": 55, "tag": "social", "location": "CEO办公室", "contact": "陈总"},
        {"title": "公司文化建设", "description": "推动公司价值观和文化建设", "difficulty": 3, "xp_reward": 40, "tag": "creative", "location": "大厅", "contact": "陈总"},
        {"title": "预算审批决策", "description": "审批各部门重大预算申请", "difficulty": 4, "xp_reward": 55, "tag": "management", "location": "CEO办公室", "contact": "陈总"},
        {"title": "危机处理方案", "description": "制定公司潜在风险应急预案", "difficulty": 5, "xp_reward": 70, "tag": "management", "location": "会议室A", "contact": "陈总"},
    ],
}

# 职级对应的难度/奖励缩放
_LEVEL_SCALING = {
    (0, 1): {"diff_add": 0, "xp_mult": 1.0},
    (2, 3): {"diff_add": 1, "xp_mult": 1.5},
    (4, 6): {"diff_add": 2, "xp_mult": 2.0},
}

# 任务链加成配置
CHAIN_BONUS = {
    2: {"xp_mult": 1.1, "label": "二连击"},   # 连续2个同类型
    3: {"xp_mult": 1.25, "label": "三连击"},  # 连续3个同类型
    4: {"xp_mult": 1.5, "label": "超级连击"},  # 连续4个+
}


def _get_scaling(career_level: int) -> dict:
    for (lo, hi), scaling in _LEVEL_SCALING.items():
        if lo <= career_level <= hi:
            return scaling
    return {"diff_add": 0, "xp_mult": 1.0}


async def _get_task_history(db: AsyncSession, agent_id: int) -> dict:
    """获取Agent的任务完成历史统计"""
    # 总完成数
    completed_result = await db.execute(
        select(sa_func.count(AgentTask.id)).where(
            AgentTask.assignee_id == agent_id,
            AgentTask.status == "completed",
        )
    )
    completed_count = completed_result.scalar() or 0

    # 总任务数（���pending/expired）
    total_result = await db.execute(
        select(sa_func.count(AgentTask.id)).where(
            AgentTask.assignee_id == agent_id,
        )
    )
    total_count = total_result.scalar() or 0

    completion_rate = int((completed_count / total_count * 100) if total_count > 0 else 100)

    # 最近5个已完成的任务标题（用于检测任务链）
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
    检测任务链：连续完成同标签类型任务的次数。
    返回 chain_count, chain_tag, bonus_info。
    """
    if not recent_tasks:
        return {"chain_count": 0, "chain_tag": None, "bonus": None}

    # 简单链检测：检查最近任务标题是否在同一模板tag中
    # 尝试匹配最近任务的tag
    title_to_tag = {}
    for t in templates:
        title_to_tag[t["title"]] = t.get("tag", "technical")

    if not recent_tasks:
        return {"chain_count": 0, "chain_tag": None, "bonus": None}

    # 获取第一个任务的tag
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

    # 取对应加成
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
    """确定性个性化任务生成：按部门选池、按职级缩放、按属性偏好排序、含任务链和自适应难度"""
    dept = profile.department
    templates = TASK_TEMPLATES.get(dept, TASK_TEMPLATES["engineering"])
    scaling = _get_scaling(profile.career_level or 0)

    # 按属性偏好排序：技术属性高优先 technical 类任务，创造力高优先 creative 类任务
    tech = profile.attr_technical or 50
    crea = profile.attr_creativity or 50
    prefer_tag = "technical" if tech >= crea else "creative"

    # 自适应难度调整
    diff_adjust = 0
    if completion_rate < 40:
        diff_adjust = -1  # 完成率低，降低难度
    elif completion_rate > 85:
        diff_adjust = 1   # 完成率高，可以加难度

    sorted_templates = sorted(
        templates,
        key=lambda t: (0 if t.get("tag") == prefer_tag else 1, random.random()),
    )

    # 如果有任务链，优先选同tag的任务作为第一个
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

        # 任务链加成：第一个任务额外奖励
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
            "location": t.get("location", "办公区"),
            "contact": t.get("contact", "上级"),
            "is_chain": is_chain,
        })
    return results


def _parse_llm_tasks(llm_result, fallback_tasks: list[dict]) -> list[dict]:
    """解析 LLM 返回的任务列表，格式不对则回退"""
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
            # LLM不生成这些字段，由fallback补充
            "location": "",
            "contact": "",
        })
    return parsed if parsed else fallback_tasks


async def generate_tasks_for_agent(
    profile: AgentProfile, db: AsyncSession, count: int = 3, use_llm: bool = True
) -> list[AgentTask]:
    """为角色生成每日任务（混合模式，含任务���和自适应难度）"""
    from app.schemas.agent_social import CAREER_LEVELS

    career_title = CAREER_LEVELS.get(profile.career_level or 0, {}).get("title", "实习生")

    # 获取任务历史
    task_history = await _get_task_history(db, profile.id)
    completion_rate = task_history["completion_rate"]

    # 检测任务链
    dept = profile.department or "engineering"
    templates = TASK_TEMPLATES.get(dept, TASK_TEMPLATES["engineering"])
    chain_info = _detect_chain(task_history["recent_tasks"], templates)

    # 确定性回退数据（含任务链和自适应难度）
    fallback = _build_personalized_tasks(
        profile, count,
        chain_info=chain_info,
        completion_rate=completion_rate,
    )

    task_data = fallback
    if use_llm:
        try:
            # 构建任务历史文本
            history_text = "暂无历史" if not task_history["recent_tasks"] else "\n".join(
                f"- {t['title']}" for t in task_history["recent_tasks"][:5]
            )

            # 构建任务链加成信息
            if chain_info.get("bonus"):
                chain_text = (
                    f"当前连续完成{chain_info['chain_count']}个{chain_info['chain_tag']}类任务，"
                    f"触发{chain_info['bonus']['label']}加成（XP x{chain_info['bonus']['xp_mult']}），"
                    f"建议继续生成同类型任务以延续连击。"
                )
            else:
                chain_text = "暂无任务链加成"

            # 推荐难度
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
        # 从fallback中获取location/contact（LLM不生成这些）
        fb = fallback[i] if i < len(fallback) else {}
        location = t.get("location") or fb.get("location", "办公区")
        contact = t.get("contact") or fb.get("contact", "上级")

        # 标注任务链
        if t.get("is_chain") and chain_info.get("bonus"):
            description = f"[{chain_info['bonus']['label']}] {description}"

        # 将地点/联系人编码到描述前缀（供前端解析展示）
        full_description = f"[地点:{location}|联系:{contact}] {description}"

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
