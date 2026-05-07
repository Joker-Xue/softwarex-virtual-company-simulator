"""
Semantic seating system - Tie character movement to meaningful locations in the office.

The seat coordinates are fully aligned with the furniture layout in companyMap.ts，formula：
  fx = room.x + room.width * item.rx
  fy = room.y + 30 + (room.height - 30) * item.ry
  encoded_y = canvas_y + (floor - 1) * FLOOR_Y_OFFSET

Levelrules：
  career_level >= 6 (CEO)      → anchored ceo_desk（anchor point），Subordinates come to the CEO Office visitor table
  career_level == 5 (Director)     → anchored director_desk（anchor point），Subordinates come to the Director Office visitor table
  career_level <= 4            → In this DepartmentdeskWork，MeetingMeeting Room，RestGo to Cafe/Lobby
"""

import random

FLOOR_Y_OFFSET = 700  # Consistent with agent_ai.py

# ---------------------------------------------------------------------------
# seat definition chart
# Field：floor, x, y（canvas coordinates），dept（Belong toDepartment），spot_type
#   anchor  - executive anchor，Not to be used by others
#   work    - Ordinary desk
#   visitor - executiveofficeVisitor's seat
#   rest    - Rest area（Cafe/Lobby）
#   meeting - Meeting room seat
#   reception - Lobbyfront desk/reception area
# ---------------------------------------------------------------------------
SPOTS: dict[str, dict] = {

    # ══════════════════════════════════════════
    # 1F  Lobby (lounge)  x=20, y=60, w=260, h=220
    # furniture：sofa@0.25,0.45 | sofa@0.75,0.45 | table@0.5,0.45 | plant*2
    # ══════════════════════════════════════════
    "lobby_reception":  {"floor": 1, "x": 150, "y": 72,  "dept": "general", "spot_type": "reception"},
    "lobby_sofa_left":  {"floor": 1, "x": 85,  "y": 176, "dept": "general", "spot_type": "rest"},
    "lobby_sofa_right": {"floor": 1, "x": 215, "y": 176, "dept": "general", "spot_type": "rest"},
    "lobby_table":      {"floor": 1, "x": 150, "y": 176, "dept": "general", "spot_type": "rest"},

    # ══════════════════════════════════════════
    # 1F  Cafe (cafeteria)  x=320, y=60, w=260, h=220
    # furniture：coffee_machine@0.5,0.15 | table@0.25,0.4 | table@0.75,0.4 | table@0.25,0.7 | table@0.75,0.7
    # ══════════════════════════════════════════
    "cafe_counter":  {"floor": 1, "x": 450, "y": 118, "dept": "general", "spot_type": "rest"},
    "cafe_table_1":  {"floor": 1, "x": 385, "y": 166, "dept": "general", "spot_type": "rest"},
    "cafe_table_2":  {"floor": 1, "x": 515, "y": 166, "dept": "general", "spot_type": "rest"},
    "cafe_table_3":  {"floor": 1, "x": 385, "y": 223, "dept": "general", "spot_type": "rest"},
    "cafe_table_4":  {"floor": 1, "x": 515, "y": 223, "dept": "general", "spot_type": "rest"},

    # ══════════════════════════════════════════
    # 1F  HR Department (office/hr)  x=20, y=340, w=560, h=220
    # furniture (office)：desk@0.2,0.35 | 0.5,0.35 | 0.8,0.35 | 0.2,0.65 | 0.5,0.65 | 0.8,0.65
    # ══════════════════════════════════════════
    "hr_desk_1": {"floor": 1, "x": 132, "y": 436, "dept": "hr", "spot_type": "work"},
    "hr_desk_2": {"floor": 1, "x": 300, "y": 436, "dept": "hr", "spot_type": "work"},
    "hr_desk_3": {"floor": 1, "x": 468, "y": 436, "dept": "hr", "spot_type": "work"},
    "hr_desk_4": {"floor": 1, "x": 132, "y": 493, "dept": "hr", "spot_type": "work"},
    "hr_desk_5": {"floor": 1, "x": 300, "y": 493, "dept": "hr", "spot_type": "work"},
    "hr_desk_6": {"floor": 1, "x": 468, "y": 493, "dept": "hr", "spot_type": "work"},
    # Interview/Visitor Seat（Center near the corridor）
    "hr_interview": {"floor": 1, "x": 300, "y": 514, "dept": "hr", "spot_type": "visitor"},

    # ══════════════════════════════════════════
    # 2F  Engineering (office/engineering)  x=20, y=60, w=155, h=280
    # furniture (office)：desk@0.2,0.35 | 0.5,0.35 | 0.8,0.35 | 0.2,0.65 | 0.5,0.65 | 0.8,0.65
    # ══════════════════════════════════════════
    "eng_desk_1": {"floor": 2, "x": 51,  "y": 177, "dept": "engineering", "spot_type": "work"},
    "eng_desk_2": {"floor": 2, "x": 97,  "y": 177, "dept": "engineering", "spot_type": "work"},
    "eng_desk_3": {"floor": 2, "x": 144, "y": 177, "dept": "engineering", "spot_type": "work"},
    "eng_desk_4": {"floor": 2, "x": 51,  "y": 252, "dept": "engineering", "spot_type": "work"},
    "eng_desk_5": {"floor": 2, "x": 97,  "y": 252, "dept": "engineering", "spot_type": "work"},
    "eng_desk_6": {"floor": 2, "x": 144, "y": 252, "dept": "engineering", "spot_type": "work"},

    # ══════════════════════════════════════════
    # 2F  Marketing (office/marketing)  x=185, y=60, w=175, h=130
    # ══════════════════════════════════════════
    "marketing_desk_1": {"floor": 2, "x": 220, "y": 125, "dept": "marketing", "spot_type": "work"},
    "marketing_desk_2": {"floor": 2, "x": 272, "y": 125, "dept": "marketing", "spot_type": "work"},
    "marketing_desk_3": {"floor": 2, "x": 325, "y": 125, "dept": "marketing", "spot_type": "work"},
    "marketing_desk_4": {"floor": 2, "x": 220, "y": 155, "dept": "marketing", "spot_type": "work"},
    "marketing_desk_5": {"floor": 2, "x": 272, "y": 155, "dept": "marketing", "spot_type": "work"},
    "marketing_desk_6": {"floor": 2, "x": 325, "y": 155, "dept": "marketing", "spot_type": "work"},

    # ══════════════════════════════════════════
    # 2F  Product (office/product)  x=185, y=200, w=175, h=140
    # ══════════════════════════════════════════
    "product_desk_1": {"floor": 2, "x": 220, "y": 268, "dept": "product", "spot_type": "work"},
    "product_desk_2": {"floor": 2, "x": 272, "y": 268, "dept": "product", "spot_type": "work"},
    "product_desk_3": {"floor": 2, "x": 325, "y": 268, "dept": "product", "spot_type": "work"},
    "product_desk_4": {"floor": 2, "x": 220, "y": 301, "dept": "product", "spot_type": "work"},
    "product_desk_5": {"floor": 2, "x": 272, "y": 301, "dept": "product", "spot_type": "work"},
    "product_desk_6": {"floor": 2, "x": 325, "y": 301, "dept": "product", "spot_type": "work"},

    # ══════════════════════════════════════════
    # 2F  Finance (office/finance)  x=370, y=60, w=170, h=130
    # ══════════════════════════════════════════
    "finance_desk_1": {"floor": 2, "x": 404, "y": 125, "dept": "finance", "spot_type": "work"},
    "finance_desk_2": {"floor": 2, "x": 455, "y": 125, "dept": "finance", "spot_type": "work"},
    "finance_desk_3": {"floor": 2, "x": 506, "y": 125, "dept": "finance", "spot_type": "work"},
    "finance_desk_4": {"floor": 2, "x": 404, "y": 155, "dept": "finance", "spot_type": "work"},
    "finance_desk_5": {"floor": 2, "x": 455, "y": 155, "dept": "finance", "spot_type": "work"},
    "finance_desk_6": {"floor": 2, "x": 506, "y": 155, "dept": "finance", "spot_type": "work"},

    # ══════════════════════════════════════════
    # 2F  Operations (office/operations)  x=370, y=200, w=170, h=140
    # ══════════════════════════════════════════
    "ops_desk_1": {"floor": 2, "x": 404, "y": 268, "dept": "operations", "spot_type": "work"},
    "ops_desk_2": {"floor": 2, "x": 455, "y": 268, "dept": "operations", "spot_type": "work"},
    "ops_desk_3": {"floor": 2, "x": 506, "y": 268, "dept": "operations", "spot_type": "work"},
    "ops_desk_4": {"floor": 2, "x": 404, "y": 301, "dept": "operations", "spot_type": "work"},
    "ops_desk_5": {"floor": 2, "x": 455, "y": 301, "dept": "operations", "spot_type": "work"},
    "ops_desk_6": {"floor": 2, "x": 506, "y": 301, "dept": "operations", "spot_type": "work"},

    # ══════════════════════════════════════════
    # 3F  Meeting Room (meeting)  x=20, y=60, w=560, h=160
    # furniture：table@0.5,0.5 | chair@0.25,0.35 | chair@0.75,0.35 | chair@0.25,0.65 | chair@0.75,0.65 | screen@0.5,0.12
    # ══════════════════════════════════════════
    "meeting_chair_1": {"floor": 3, "x": 160, "y": 135, "dept": "general", "spot_type": "meeting"},
    "meeting_chair_2": {"floor": 3, "x": 240, "y": 135, "dept": "general", "spot_type": "meeting"},
    "meeting_chair_3": {"floor": 3, "x": 340, "y": 135, "dept": "general", "spot_type": "meeting"},
    "meeting_chair_4": {"floor": 3, "x": 440, "y": 135, "dept": "general", "spot_type": "meeting"},
    "meeting_chair_5": {"floor": 3, "x": 160, "y": 175, "dept": "general", "spot_type": "meeting"},
    "meeting_chair_6": {"floor": 3, "x": 240, "y": 175, "dept": "general", "spot_type": "meeting"},
    "meeting_chair_7": {"floor": 3, "x": 340, "y": 175, "dept": "general", "spot_type": "meeting"},
    "meeting_chair_8": {"floor": 3, "x": 440, "y": 175, "dept": "general", "spot_type": "meeting"},

    # ══════════════════════════════════════════
    # 3F  Director Office (office/management)  x=20, y=280, w=260, h=260
    # furniture (office)：use central desk as"Director seat"anchor point
    # ══════════════════════════════════════════
    "director_desk":      {"floor": 3, "x": 150, "y": 390, "dept": "management", "spot_type": "anchor"},
    "director_visitor_1": {"floor": 3, "x": 72,  "y": 459, "dept": "management", "spot_type": "visitor"},
    "director_visitor_2": {"floor": 3, "x": 150, "y": 459, "dept": "management", "spot_type": "visitor"},
    "director_visitor_3": {"floor": 3, "x": 228, "y": 459, "dept": "management", "spot_type": "visitor"},

    # ══════════════════════════════════════════
    # 3F  CEO Office (ceo_office/management)  x=320, y=280, w=260, h=260
    # furniture：desk@0.5,0.35 | bookshelf*2 | sofa@0.3,0.75 | plant
    # ══════════════════════════════════════════
    "ceo_desk":      {"floor": 3, "x": 450, "y": 390, "dept": "management", "spot_type": "anchor"},
    "ceo_sofa":      {"floor": 3, "x": 398, "y": 482, "dept": "management", "spot_type": "visitor"},
    "ceo_visitor_1": {"floor": 3, "x": 450, "y": 482, "dept": "management", "spot_type": "visitor"},
    "ceo_visitor_2": {"floor": 3, "x": 500, "y": 482, "dept": "management", "spot_type": "visitor"},
}


# ---------------------------------------------------------------------------
# Precomputed encoded Y coordinate（Avoid double counting）
# ---------------------------------------------------------------------------
for _name, _s in SPOTS.items():
    _s["encoded_y"] = _s["y"] + (_s["floor"] - 1) * FLOOR_Y_OFFSET

# ---------------------------------------------------------------------------
# Quick lookup table grouped by Department/Type
# ---------------------------------------------------------------------------
_DEPT_WORK_SPOTS: dict[str, list[str]] = {}
_REST_SPOTS: list[str] = []
_MEETING_SPOTS: list[str] = []
_LOBBY_SPOTS: list[str] = []
_SPOTS_BY_FLOOR: dict[int, list[str]] = {}
_NON_ANCHOR_SPOTS: list[str] = []

for _name, _s in SPOTS.items():
    t = _s["spot_type"]
    d = _s["dept"]
    _SPOTS_BY_FLOOR.setdefault(_s["floor"], []).append(_name)
    if t != "anchor":
        _NON_ANCHOR_SPOTS.append(_name)
    if t == "work":
        _DEPT_WORK_SPOTS.setdefault(d, []).append(_name)
    elif t == "rest":
        if d == "general" and _s["floor"] == 1:
            if _name.startswith("cafe_"):
                _REST_SPOTS.append(_name)
            else:
                _LOBBY_SPOTS.append(_name)
    elif t == "meeting":
        _MEETING_SPOTS.append(_name)

# HR reception Also considered a LobbySocial area
_LOBBY_SPOTS.append("lobby_reception")


def _decode_floor(encoded_y: int) -> int:
    floor = encoded_y // FLOOR_Y_OFFSET + 1
    return max(1, min(3, floor))


def _decode_canvas_y(encoded_y: int) -> int:
    return encoded_y % FLOOR_Y_OFFSET


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_spot_pos(spot_name: str) -> tuple[int, int]:
    """Back (pos_x, encoded_pos_y) For writing directly to AgentProfile."""
    s = SPOTS[spot_name]
    return (s["x"], s["encoded_y"])


def get_spot_name_by_pos(pos_x: int, encoded_pos_y: int) -> str | None:
    """Check the seat name based on the coordinates（exact match）。"""
    for name, spot in SPOTS.items():
        if spot["x"] == pos_x and spot["encoded_y"] == encoded_pos_y:
            return name
    return None


def get_work_spots(department: str) -> list[str]:
    """BackList of all desk names of the specified Department."""
    return list(_DEPT_WORK_SPOTS.get(department, []))


def assign_work_spot(department: str, agent_id: int) -> str | None:
    """
    Assign a deterministic desk to the agent（Use agent_id to take the model to ensure that the same agent always goes to the same table）。
    If Department does not have a desk definition，Back None。
    """
    spots = _DEPT_WORK_SPOTS.get(department, [])
    if not spots:
        return None
    return spots[agent_id % len(spots)]


def assign_rest_spot(agent_id: int | None = None) -> str:
    """Back a Cafe seat（can be sorted by agent_id deterministic assignment）。"""
    if agent_id is not None:
        return _REST_SPOTS[agent_id % len(_REST_SPOTS)]
    return random.choice(_REST_SPOTS)


def assign_lobby_spot(agent_id: int | None = None) -> str:
    """Back a Lobby leisure space（can be sorted by agent_id deterministic assignment）。"""
    if agent_id is not None:
        return _LOBBY_SPOTS[agent_id % len(_LOBBY_SPOTS)]
    return random.choice(_LOBBY_SPOTS)


def assign_meeting_spot(agent_id: int | None = None) -> str:
    """BackaMeeting room seat（If agent_id is provided then deterministic assignment）."""
    if agent_id is not None:
        return _MEETING_SPOTS[agent_id % len(_MEETING_SPOTS)]
    return random.choice(_MEETING_SPOTS)


def _is_management_track(
    department: str | None,
    career_path: str | None = None,
) -> bool:
    dept = (department or "").strip().lower()
    return dept == "management"


def get_anchor_spot(
    career_level: int,
    department: str | None = None,
    career_path: str | None = None,
) -> str | None:
    """
    Backexecutive anchor point seat name.
    Only management line roles can use executive anchor：
    - CEO (level>=6) → ceo_desk
    - Director (level==5) → director_desk
    """
    if not _is_management_track(department, career_path):
        return None
    if career_level >= 6:
        return "ceo_desk"
    if career_level == 5:
        return "director_desk"
    return None


def is_anchor_role(
    career_level: int,
    department: str | None = None,
    career_path: str | None = None,
) -> bool:
    """JudgingWhether it is anchoredexecutive（Only manage lines level>=5）。"""
    return career_level >= 5 and _is_management_track(department, career_path)


def get_visitor_spots(career_level: int) -> list[str]:
    """
    BackList of guest seats that can be seated when visiting the corresponding executive level。
    CEOreport  CEO office visitor seat；Report to Director → Director office visitor seat。
    """
    if career_level >= 6:
        return ["ceo_sofa", "ceo_visitor_1", "ceo_visitor_2"]
    if career_level == 5:
        return ["director_visitor_1", "director_visitor_2", "director_visitor_3"]
    return []


def spot_to_room_name(spot_name: str) -> str:
    """Map seat names to Chinese room names，Used for log and Memories content."""
    if spot_name.startswith("lobby_"):
        return "Lobby"
    if spot_name.startswith("cafe_"):
        return "Cafe"
    if spot_name.startswith("hr_"):
        return "HR Department"
    if spot_name.startswith("eng_"):
        return "Engineering"
    if spot_name.startswith("marketing_"):
        return "Marketing"
    if spot_name.startswith("product_"):
        return "Product"
    if spot_name.startswith("finance_"):
        return "Finance"
    if spot_name.startswith("ops_"):
        return "Operations"
    if spot_name.startswith("meeting_"):
        return "Meeting Room"
    if spot_name.startswith("director_"):
        return "Director Office"
    if spot_name.startswith("ceo_"):
        return "CEO Office"
    return spot_name


def get_movable_spot_names(
    career_level: int,
    department: str | None = None,
    career_path: str | None = None,
) -> list[str]:
    """
    Back This role allows the collection of seats to stay.
    - default：All non-anchor point bits
    - executive：Additional permission for your own anchor point
    """
    spots = list(_NON_ANCHOR_SPOTS)
    anchor = get_anchor_spot(career_level, department, career_path)
    if anchor:
        spots.append(anchor)
    return spots


def snap_to_nearest_spot(
    x: int,
    encoded_y: int,
    career_level: int,
    department: str | None = None,
    career_path: str | None = None,
) -> str:
    """
    Snap arbitrary coordinates to the nearest legal semantic seat。
    Prioritize adsorption within the target floor；If there are no candidates for the target floor，fallbackoverall situation
    """
    target_floor = _decode_floor(encoded_y)
    target_canvas_y = _decode_canvas_y(encoded_y)
    movable = set(get_movable_spot_names(career_level, department, career_path))
    floor_candidates = [n for n in _SPOTS_BY_FLOOR.get(target_floor, []) if n in movable]
    candidates = floor_candidates if floor_candidates else [n for n in SPOTS.keys() if n in movable]

    best_name = candidates[0]
    best_dist = 10**18
    for name in candidates:
        spot = SPOTS[name]
        dx = x - spot["x"]
        dy = target_canvas_y - spot["y"]
        dist = dx * dx + dy * dy
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


def get_task_target_spot(
    *,
    department: str,
    career_level: int,
    career_path: str | None,
    agent_id: int,
    task_type: str | None,
    task_title: str | None,
) -> str:
    """
    Assign target seats based on Task semantics，Make sure the characters land at meaningful points。
    """
    if is_anchor_role(career_level, department, career_path):
        anchor = get_anchor_spot(career_level, department, career_path)
        if anchor:
            return anchor

    text = ((task_type or "") + " " + (task_title or "")).lower()
    meeting_keywords = ("meeting", "sync", "review", "report", "Meeting", "Review", "Review", "Training")
    hr_keywords = ("interview", "recruit", "hire", "onboard", "recruitment", "interview", "Onboarding")
    social_keywords = ("social", "collab", "communicate", "cooperation", "Social", "Team Building")
    rest_keywords = ("break", "lunch", "coffee", "Rest", "lunch", "break")

    if any(k in text for k in meeting_keywords):
        return assign_meeting_spot(agent_id)
    if any(k in text for k in hr_keywords):
        if department == "hr":
            return "hr_interview"
        return assign_meeting_spot(agent_id)
    if any(k in text for k in social_keywords):
        return assign_lobby_spot(agent_id) if agent_id % 2 == 0 else assign_rest_spot(agent_id)
    if any(k in text for k in rest_keywords):
        return assign_rest_spot(agent_id)

    work_spot = assign_work_spot(department, agent_id)
    if work_spot:
        return work_spot
    return "lobby_reception"


def get_after_work_spot(
    *,
    agent_id: int,
    department: str,
    career_level: int,
    career_path: str | None = None,
) -> str:
    """
    get off Allocation of stay points after work.
    To avoid everyone stacking at the same point，and maintain multi-floor visibility：
    - executive returns to his anchor point office first；
    - regular Staff are deterministically dispersed at three types of locations: "Departmentdesk/Lobby/Cafe" according to agent_id.
    """
    anchor = get_anchor_spot(career_level, department, career_path)
    if anchor:
        return anchor

    mod = agent_id % 3
    if mod == 0:
        work_spot = assign_work_spot(department, agent_id)
        if work_spot:
            return work_spot
    if mod == 1:
        return assign_lobby_spot(agent_id)
    return assign_rest_spot(agent_id)
