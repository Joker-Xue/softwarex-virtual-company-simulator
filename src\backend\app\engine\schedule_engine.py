"""
AI日程引擎 - 根据MBTI性格类型生成每日日程
C-16: AI Schedule Engine
"""
import random
from datetime import datetime, timedelta

# J型MBTI类型列表（判断型：严格固定时间）
J_TYPES = {"ISTJ", "INTJ", "ESTJ", "ENTJ", "ISFJ", "INFJ", "ESFJ", "ENFJ"}
# P型MBTI类型列表（感知型：灵活随性）
P_TYPES = {"ISTP", "INTP", "ESTP", "ENTP", "ISFP", "INFP", "ESFP", "ENFP"}

# 标准时间块定义：(小时, 分钟, 活动名, 房间类型)
BASE_SCHEDULE = [
    (9, 0, "工作", "office"),
    (10, 30, "休息", "cafeteria"),
    (11, 0, "工作", "office"),
    (12, 0, "午餐", "cafeteria"),
    (13, 30, "工作", "office"),
    (15, 30, "茶歇", "cafeteria"),
    (16, 0, "工作", "office"),
    (17, 0, "社交", "lounge"),
    (18, 0, "下班", "lounge"),
]

# 活动到Agent动作的映射
ACTIVITY_TO_ACTION = {
    "工作": "work",
    "休息": "rest",
    "午餐": "rest",
    "茶歇": "rest",
    "社交": "chat",
    "下班": "idle",
}

# 活动到目标房间的映射（默认）
ACTIVITY_TO_ROOM = {
    "工作": "office",
    "休息": "cafeteria",
    "午餐": "cafeteria",
    "茶歇": "cafeteria",
    "社交": "lounge",
    "下班": "lounge",
}


def _apply_variance(hour: int, minute: int, max_offset_minutes: int) -> str:
    """对时间施加随机偏移，返回 HH:MM 格式字符串"""
    base = datetime(2000, 1, 1, hour, minute)
    offset = random.randint(-max_offset_minutes, max_offset_minutes)
    result = base + timedelta(minutes=offset)
    # 确保时间在合理范围内（不早于8:00，不晚于20:00）
    earliest = datetime(2000, 1, 1, 8, 0)
    latest = datetime(2000, 1, 1, 20, 0)
    if result < earliest:
        result = earliest
    elif result > latest:
        result = latest
    return result.strftime("%H:%M")


def generate_daily_schedule(agent_profile) -> list[dict]:
    """
    根据MBTI性格类型生成24小时日程安排。

    J类型（判断型）：严格固定时间，时间偏移 +/-5分钟
    P类型（感知型）：灵活随性，时间偏移 +/-30分钟

    参数:
        agent_profile: AgentProfile对象或含有 mbti 属性的字典/对象

    返回:
        日程列表，每项包含 {"time": "HH:MM", "activity": "...", "room_type": "..."}
    """
    # 支持dict或对象两种传入方式
    if isinstance(agent_profile, dict):
        mbti = agent_profile.get("mbti", "INTJ")
    else:
        mbti = getattr(agent_profile, "mbti", "INTJ")

    mbti = mbti.upper() if mbti else "INTJ"

    # 根据J/P维度决定时间偏移范围
    if len(mbti) >= 4 and mbti[3] == "J":
        max_offset = 5   # J型：严格，仅 +/-5分钟
    else:
        max_offset = 30  # P型：灵活，+/-30分钟

    schedule = []
    for hour, minute, activity, room_type in BASE_SCHEDULE:
        time_str = _apply_variance(hour, minute, max_offset)
        schedule.append({
            "time": time_str,
            "activity": activity,
            "room_type": room_type,
        })

    # 按时间排序，避免偏移导致乱序
    schedule.sort(key=lambda x: x["time"])

    return schedule


def get_current_scheduled_activity(schedule: list[dict]) -> dict | None:
    """
    根据当前时间查找日程中应当进行的活动。

    遍历日程找到当前时间所在的时间段（即最后一个 time <= 当前时间的条目）。

    返回:
        匹配的日程条目 {"time", "activity", "room_type"} 或 None
    """
    if not schedule:
        return None

    now = datetime.now().strftime("%H:%M")

    current_entry = None
    for entry in schedule:
        # 跳过内部状态项（_sim_state, _decision_log 等非日程条目）
        if not isinstance(entry, dict) or "time" not in entry:
            continue
        if entry["time"] <= now:
            current_entry = entry
        else:
            break

    return current_entry


def get_action_for_activity(activity: str) -> str:
    """将日程活动名映射为Agent动作类型"""
    return ACTIVITY_TO_ACTION.get(activity, "idle")


def get_room_for_activity(activity: str) -> str:
    """将日程活动名映射为默认目标房间类型"""
    return ACTIVITY_TO_ROOM.get(activity, "lounge")
