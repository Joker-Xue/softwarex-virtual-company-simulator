"""
AIengine - Generate daily schedule based on MBTIpersonality type
C-16: AI Schedule Engine
"""
import random
from datetime import datetime, timedelta

# JMBTI type list（Judging type：strict fixed time）
J_TYPES = {"ISTJ", "INTJ", "ESTJ", "ENTJ", "ISFJ", "INFJ", "ESFJ", "ENFJ"}
# PMBTI type list（Perceiving type：flexible and spontaneous）
P_TYPES = {"ISTP", "INTP", "ESTP", "ENTP", "ISFP", "INFP", "ESFP", "ENFP"}

# Standard time block definition：(Hour, minutes, Activity, Room type)
BASE_SCHEDULE = [
    (9, 0, "Work", "office"),
    (10, 30, "Rest", "cafeteria"),
    (11, 0, "Work", "office"),
    (12, 0, "lunch", "cafeteria"),
    (13, 30, "Work", "office"),
    (15, 30, "break", "cafeteria"),
    (16, 0, "Work", "office"),
    (17, 0, "Social", "lounge"),
    (18, 0, "get off work", "lounge"),
]

# Activity to Agent action mapping
ACTIVITY_TO_ACTION = {
    "Work": "work",
    "Rest": "rest",
    "lunch": "rest",
    "break": "rest",
    "Social": "chat",
    "get off work": "idle",
}

# Mapping of Activity to target room（default）
ACTIVITY_TO_ROOM = {
    "Work": "office",
    "Rest": "cafeteria",
    "lunch": "cafeteria",
    "break": "cafeteria",
    "Social": "lounge",
    "get off work": "lounge",
}


def _apply_variance(hour: int, minute: int, max_offset_minutes: int) -> str:
    """Apply a random offset to time，Back HH:MM format string"""
    base = datetime(2000, 1, 1, hour, minute)
    offset = random.randint(-max_offset_minutes, max_offset_minutes)
    result = base + timedelta(minutes=offset)
    # Make sure the time is within a reasonable range（No earlier than 8:00，No later than 20:00）
    earliest = datetime(2000, 1, 1, 8, 0)
    latest = datetime(2000, 1, 1, 20, 0)
    if result < earliest:
        result = earliest
    elif result > latest:
        result = latest
    return result.strftime("%H:%M")


def generate_daily_schedule(agent_profile) -> list[dict]:
    """
    Generate 24-hour schedule based on MBTIpersonality type。

    Jtype（Judging type）：strict fixed time，time offset +/-5minutes
    Ptype（Perceiving type）：flexible and spontaneous，time offset +/-30minutes

    parameter:
        agent_profile: AgentProfile object or dictionary/object containing mbti attribute

    Back:
        schedule list，Include each item {"time": "HH:MM", "activity": "...", "room_type": "..."}
    """
    # Supports two input methods: dict or object
    if isinstance(agent_profile, dict):
        mbti = agent_profile.get("mbti", "INTJ")
    else:
        mbti = getattr(agent_profile, "mbti", "INTJ")

    mbti = mbti.upper() if mbti else "INTJ"

    # Determine the time offset range based on the J/P dimension
    if len(mbti) >= 4 and mbti[3] == "J":
        max_offset = 5   # J type：strict，+/-5minutes only
    else:
        max_offset = 30  # P type：flexible，+/-30minutes

    schedule = []
    for hour, minute, activity, room_type in BASE_SCHEDULE:
        time_str = _apply_variance(hour, minute, max_offset)
        schedule.append({
            "time": time_str,
            "activity": activity,
            "room_type": room_type,
        })

    # Sort by time，Avoid offsets causing disorder
    schedule.sort(key=lambda x: x["time"])

    return schedule


def get_current_scheduled_activity(schedule: list[dict]) -> dict | None:
    """
    Find the activities that should be performed in the schedule based on the Current time.

    Traverse the schedule to find the time segment where the Current time is located（That is, the last msgs item with time <= Current time）。

    Back:
        matching schedule msgs item {"time", "activity", "room_type"} or None
    """
    if not schedule:
        return None

    now = datetime.now().strftime("%H:%M")

    current_entry = None
    for entry in schedule:
        # Skip internal state items（_sim_state, _decision_log Waiting for non-scheduled msgs eyes）
        if not isinstance(entry, dict) or "time" not in entry:
            continue
        if entry["time"] <= now:
            current_entry = entry
        else:
            break

    return current_entry


def get_action_for_activity(activity: str) -> str:
    """Map schedule activity name to Agent action type"""
    return ACTIVITY_TO_ACTION.get(activity, "idle")


def get_room_for_activity(activity: str) -> str:
    """Map the schedule event name to the default target room type"""
    return ACTIVITY_TO_ROOM.get(activity, "lounge")
