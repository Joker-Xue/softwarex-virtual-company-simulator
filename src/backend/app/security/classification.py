"""
Pillar 1：data classification and classification engine

four-level classification system，Drive encryption, auditing, and access control decisions.
conform to《Personal Information Protection Act》(PIPL) data classification and grading requirements。
"""
from enum import IntEnum
from functools import wraps
from typing import Optional

from fastapi import HTTPException, status


class DataLevel(IntEnum):
    """data sensitivity level（The larger the value, the more sensitive it is）"""
    PUBLIC = 1        # public data：Job title、Game progress, etc.
    INTERNAL = 2      # Internal data：File path, Agentinformation, User Preference
    CONFIDENTIAL = 3  # Confidential data：email、Phone number、Name、Original resume、Conversation content
    TOP_SECRET = 4    # Top secret data：passwordID numberbank card number


# ---------------------------------------------------------------------------
# overall situationdata classification register table
# Mapping: (table name, Field name) -> DataLevel
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

    # ── job_portraits (public data) ──
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
    """Query the sensitivity level of the field，Unregistered fields default to INTERNAL"""
    return DATA_CLASSIFICATION_REGISTRY.get((table, field), DataLevel.INTERNAL)


def get_table_max_level(table: str) -> DataLevel:
    """Get the highest sensitivity level in the table"""
    levels = [
        level for (t, _), level in DATA_CLASSIFICATION_REGISTRY.items()
        if t == table
    ]
    return max(levels) if levels else DataLevel.INTERNAL


def get_fields_by_level(level: DataLevel) -> list[tuple[str, str]]:
    """Get all fields at the specified level"""
    return [
        (table, field)
        for (table, field), lvl in DATA_CLASSIFICATION_REGISTRY.items()
        if lvl == level
    ]


def classify_access(min_level: DataLevel):
    """
    Route-level access control decorator。

    Current UserDo you have permission to access data at a specified level of sensitivity?
    - PUBLIC: Accessible to everyone
    - INTERNAL: Login required
    - CONFIDENTIAL: Requires login and data owner
    - TOP_SECRET: managers only
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs（FastAPI dependency injection）
            current_user = kwargs.get("current_user")

            if min_level == DataLevel.PUBLIC:
                return await func(*args, **kwargs)

            if min_level >= DataLevel.INTERNAL and current_user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="A login is required to access this resource",
                )

            if min_level >= DataLevel.TOP_SECRET:
                if not getattr(current_user, "is_admin", False):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Insufficient permissions：Requires manager permissions",
                    )

            return await func(*args, **kwargs)
        return wrapper
    return decorator
