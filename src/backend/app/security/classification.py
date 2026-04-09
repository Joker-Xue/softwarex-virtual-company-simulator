"""
支柱1：数据分类分级引擎

四级分类体系，驱动加密、审计、访问控制决策。
符合《个人信息保护法》(PIPL) 数据分类分级要求。
"""
from enum import IntEnum
from functools import wraps
from typing import Optional

from fastapi import HTTPException, status


class DataLevel(IntEnum):
    """数据敏感等级（值越大越敏感）"""
    PUBLIC = 1        # 公开数据：岗位名称、游戏进度等
    INTERNAL = 2      # 内部数据：文件路径、Agent消息、用户偏好
    CONFIDENTIAL = 3  # 机密数据：邮箱、手机号、姓名、简历原文、对话内容
    TOP_SECRET = 4    # 绝密数据：密码哈希、身份证号、银行卡号


# ---------------------------------------------------------------------------
# 全局数据分类注册表
# 映射: (表名, 字段名) -> DataLevel
# ---------------------------------------------------------------------------
DATA_CLASSIFICATION_REGISTRY: dict[tuple[str, str], DataLevel] = {
    # ── users ──
    ("users", "id"): DataLevel.INTERNAL,
    ("users", "username"): DataLevel.INTERNAL,
    ("users", "email"): DataLevel.CONFIDENTIAL,
    ("users", "password_hash"): DataLevel.TOP_SECRET,
    ("users", "full_name"): DataLevel.CONFIDENTIAL,
    ("users", "phone"): DataLevel.CONFIDENTIAL,
    ("users", "is_active"): DataLevel.INTERNAL,
    ("users", "is_admin"): DataLevel.INTERNAL,
    ("users", "created_at"): DataLevel.PUBLIC,
    ("users", "updated_at"): DataLevel.PUBLIC,

    # ── student_portraits ──
    ("student_portraits", "name"): DataLevel.CONFIDENTIAL,
    ("student_portraits", "phone"): DataLevel.CONFIDENTIAL,
    ("student_portraits", "email"): DataLevel.CONFIDENTIAL,
    ("student_portraits", "resume_text"): DataLevel.CONFIDENTIAL,
    ("student_portraits", "school"): DataLevel.INTERNAL,
    ("student_portraits", "major"): DataLevel.INTERNAL,
    ("student_portraits", "skills"): DataLevel.INTERNAL,
    ("student_portraits", "analysis"): DataLevel.INTERNAL,
    ("student_portraits", "strengths"): DataLevel.INTERNAL,
    ("student_portraits", "weaknesses"): DataLevel.INTERNAL,
    ("student_portraits", "dimensions"): DataLevel.INTERNAL,
    ("student_portraits", "growth_prediction"): DataLevel.INTERNAL,

    # ── resumes ──
    ("resumes", "raw_text"): DataLevel.CONFIDENTIAL,
    ("resumes", "parsed_data"): DataLevel.CONFIDENTIAL,
    ("resumes", "file_path"): DataLevel.INTERNAL,
    ("resumes", "file_name"): DataLevel.INTERNAL,
    ("resumes", "education"): DataLevel.INTERNAL,
    ("resumes", "work_experience"): DataLevel.INTERNAL,
    ("resumes", "skills"): DataLevel.INTERNAL,

    # ── chat_history ──
    ("chat_history", "content"): DataLevel.CONFIDENTIAL,
    ("chat_history", "context"): DataLevel.INTERNAL,
    ("chat_history", "session_id"): DataLevel.INTERNAL,

    # ── career_reports ──
    ("career_reports", "match_analysis"): DataLevel.CONFIDENTIAL,
    ("career_reports", "full_content"): DataLevel.CONFIDENTIAL,
    ("career_reports", "career_goal"): DataLevel.INTERNAL,

    # ── match_results ──
    ("match_results", "basic_analysis"): DataLevel.INTERNAL,
    ("match_results", "skill_analysis"): DataLevel.INTERNAL,
    ("match_results", "total_score"): DataLevel.INTERNAL,

    # ── interview_sessions ──
    ("interview_sessions", "conversation"): DataLevel.CONFIDENTIAL,
    ("interview_sessions", "feedback"): DataLevel.INTERNAL,

    # ── password_reset_tokens ──
    ("password_reset_tokens", "token"): DataLevel.TOP_SECRET,

    # ── agent_messages ──
    ("agent_messages", "content"): DataLevel.INTERNAL,

    # ── job_portraits (公开数据) ──
    ("job_infos", "job_title"): DataLevel.PUBLIC,
    ("job_infos", "job_category"): DataLevel.PUBLIC,
    ("job_infos", "salary_range"): DataLevel.PUBLIC,
    ("job_infos", "required_skills"): DataLevel.PUBLIC,
    ("job_infos", "industry"): DataLevel.PUBLIC,

    # ── game_progress ──
    ("game_progress", "current_level"): DataLevel.PUBLIC,
    ("game_progress", "total_score"): DataLevel.PUBLIC,

    # ── coin_transactions ──
    ("coin_transactions", "amount"): DataLevel.INTERNAL,
    ("coin_transactions", "type"): DataLevel.INTERNAL,

    # ── sandbox_scenarios ──
    ("sandbox_scenarios", "scenario_data"): DataLevel.INTERNAL,
    ("sandbox_scenarios", "result"): DataLevel.INTERNAL,

    # ── feedback ──
    ("feedback", "content"): DataLevel.INTERNAL,
}


def get_field_level(table: str, field: str) -> DataLevel:
    """查询字段的敏感等级，未注册字段默认为 INTERNAL"""
    return DATA_CLASSIFICATION_REGISTRY.get((table, field), DataLevel.INTERNAL)


def get_table_max_level(table: str) -> DataLevel:
    """获取表中最高敏感等级"""
    levels = [
        level for (t, _), level in DATA_CLASSIFICATION_REGISTRY.items()
        if t == table
    ]
    return max(levels) if levels else DataLevel.INTERNAL


def get_fields_by_level(level: DataLevel) -> list[tuple[str, str]]:
    """获取指定等级的所有字段"""
    return [
        (table, field)
        for (table, field), lvl in DATA_CLASSIFICATION_REGISTRY.items()
        if lvl == level
    ]


def classify_access(min_level: DataLevel):
    """
    路由级访问控制装饰器。

    检查当前用户是否有权访问指定敏感等级的数据。
    - PUBLIC: 所有人可访问
    - INTERNAL: 需要登录
    - CONFIDENTIAL: 需要登录且为数据所有者
    - TOP_SECRET: 仅管理员
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从 kwargs 中提取 current_user（FastAPI 依赖注入）
            current_user = kwargs.get("current_user")

            if min_level == DataLevel.PUBLIC:
                return await func(*args, **kwargs)

            if min_level >= DataLevel.INTERNAL and current_user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="需要登录才能访问此资源",
                )

            if min_level >= DataLevel.TOP_SECRET:
                if not getattr(current_user, "is_admin", False):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="权限不足：需要管理员权限",
                    )

            return await func(*args, **kwargs)
        return wrapper
    return decorator
