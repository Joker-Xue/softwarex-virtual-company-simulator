"""
语义化座位系统 - 将人物移动与办公室中有实际意义的位置绑定。

座位坐标与 companyMap.ts 中的家具布局完全对齐，公式：
  fx = room.x + room.width * item.rx
  fy = room.y + 30 + (room.height - 30) * item.ry
  encoded_y = canvas_y + (floor - 1) * FLOOR_Y_OFFSET

职级规则：
  career_level >= 6 (CEO)      → 常驻 ceo_desk（锚点），下属来CEO办公室 visitor 席
  career_level == 5 (总监)     → 常驻 director_desk（锚点），下属来总监办公室 visitor 席
  career_level <= 4            → 在本部门工位工作，会议去会议室，休息去咖啡厅/大厅
"""

import random

FLOOR_Y_OFFSET = 700  # 与 agent_ai.py 保持一致

# ---------------------------------------------------------------------------
# 座位定义表
# 字段：floor, x, y（画布坐标），dept（归属部门），spot_type
#   anchor  - 高管锚点，不可被其他人使用
#   work    - 普通工位
#   visitor - 高管办公室访客席
#   rest    - 休息区（咖啡厅/大厅）
#   meeting - 会议室座椅
#   reception - 大厅前台/接待区
# ---------------------------------------------------------------------------
SPOTS: dict[str, dict] = {

    # ══════════════════════════════════════════
    # 1F  大厅 (lounge)  x=20, y=60, w=260, h=220
    # 家具：sofa@0.25,0.45 | sofa@0.75,0.45 | table@0.5,0.45 | plant*2
    # ══════════════════════════════════════════
    "lobby_reception":  {"floor": 1, "x": 150, "y": 72,  "dept": "general", "spot_type": "reception"},
    "lobby_sofa_left":  {"floor": 1, "x": 85,  "y": 176, "dept": "general", "spot_type": "rest"},
    "lobby_sofa_right": {"floor": 1, "x": 215, "y": 176, "dept": "general", "spot_type": "rest"},
    "lobby_table":      {"floor": 1, "x": 150, "y": 176, "dept": "general", "spot_type": "rest"},

    # ══════════════════════════════════════════
    # 1F  咖啡厅 (cafeteria)  x=320, y=60, w=260, h=220
    # 家具：coffee_machine@0.5,0.15 | table@0.25,0.4 | table@0.75,0.4 | table@0.25,0.7 | table@0.75,0.7
    # ══════════════════════════════════════════
    "cafe_counter":  {"floor": 1, "x": 450, "y": 118, "dept": "general", "spot_type": "rest"},
    "cafe_table_1":  {"floor": 1, "x": 385, "y": 166, "dept": "general", "spot_type": "rest"},
    "cafe_table_2":  {"floor": 1, "x": 515, "y": 166, "dept": "general", "spot_type": "rest"},
    "cafe_table_3":  {"floor": 1, "x": 385, "y": 223, "dept": "general", "spot_type": "rest"},
    "cafe_table_4":  {"floor": 1, "x": 515, "y": 223, "dept": "general", "spot_type": "rest"},

    # ══════════════════════════════════════════
    # 1F  HR部门 (office/hr)  x=20, y=340, w=560, h=220
    # 家具 (office)：desk@0.2,0.35 | 0.5,0.35 | 0.8,0.35 | 0.2,0.65 | 0.5,0.65 | 0.8,0.65
    # ══════════════════════════════════════════
    "hr_desk_1": {"floor": 1, "x": 132, "y": 436, "dept": "hr", "spot_type": "work"},
    "hr_desk_2": {"floor": 1, "x": 300, "y": 436, "dept": "hr", "spot_type": "work"},
    "hr_desk_3": {"floor": 1, "x": 468, "y": 436, "dept": "hr", "spot_type": "work"},
    "hr_desk_4": {"floor": 1, "x": 132, "y": 493, "dept": "hr", "spot_type": "work"},
    "hr_desk_5": {"floor": 1, "x": 300, "y": 493, "dept": "hr", "spot_type": "work"},
    "hr_desk_6": {"floor": 1, "x": 468, "y": 493, "dept": "hr", "spot_type": "work"},
    # 面试/来访者席（中央靠近走廊处）
    "hr_interview": {"floor": 1, "x": 300, "y": 514, "dept": "hr", "spot_type": "visitor"},

    # ══════════════════════════════════════════
    # 2F  工程部 (office/engineering)  x=20, y=60, w=155, h=280
    # 家具 (office)：desk@0.2,0.35 | 0.5,0.35 | 0.8,0.35 | 0.2,0.65 | 0.5,0.65 | 0.8,0.65
    # ══════════════════════════════════════════
    "eng_desk_1": {"floor": 2, "x": 51,  "y": 177, "dept": "engineering", "spot_type": "work"},
    "eng_desk_2": {"floor": 2, "x": 97,  "y": 177, "dept": "engineering", "spot_type": "work"},
    "eng_desk_3": {"floor": 2, "x": 144, "y": 177, "dept": "engineering", "spot_type": "work"},
    "eng_desk_4": {"floor": 2, "x": 51,  "y": 252, "dept": "engineering", "spot_type": "work"},
    "eng_desk_5": {"floor": 2, "x": 97,  "y": 252, "dept": "engineering", "spot_type": "work"},
    "eng_desk_6": {"floor": 2, "x": 144, "y": 252, "dept": "engineering", "spot_type": "work"},

    # ══════════════════════════════════════════
    # 2F  市场部 (office/marketing)  x=185, y=60, w=175, h=130
    # ══════════════════════════════════════════
    "marketing_desk_1": {"floor": 2, "x": 220, "y": 125, "dept": "marketing", "spot_type": "work"},
    "marketing_desk_2": {"floor": 2, "x": 272, "y": 125, "dept": "marketing", "spot_type": "work"},
    "marketing_desk_3": {"floor": 2, "x": 325, "y": 125, "dept": "marketing", "spot_type": "work"},
    "marketing_desk_4": {"floor": 2, "x": 220, "y": 155, "dept": "marketing", "spot_type": "work"},
    "marketing_desk_5": {"floor": 2, "x": 272, "y": 155, "dept": "marketing", "spot_type": "work"},
    "marketing_desk_6": {"floor": 2, "x": 325, "y": 155, "dept": "marketing", "spot_type": "work"},

    # ══════════════════════════════════════════
    # 2F  产品部 (office/product)  x=185, y=200, w=175, h=140
    # ══════════════════════════════════════════
    "product_desk_1": {"floor": 2, "x": 220, "y": 268, "dept": "product", "spot_type": "work"},
    "product_desk_2": {"floor": 2, "x": 272, "y": 268, "dept": "product", "spot_type": "work"},
    "product_desk_3": {"floor": 2, "x": 325, "y": 268, "dept": "product", "spot_type": "work"},
    "product_desk_4": {"floor": 2, "x": 220, "y": 301, "dept": "product", "spot_type": "work"},
    "product_desk_5": {"floor": 2, "x": 272, "y": 301, "dept": "product", "spot_type": "work"},
    "product_desk_6": {"floor": 2, "x": 325, "y": 301, "dept": "product", "spot_type": "work"},

    # ══════════════════════════════════════════
    # 2F  财务部 (office/finance)  x=370, y=60, w=170, h=130
    # ══════════════════════════════════════════
    "finance_desk_1": {"floor": 2, "x": 404, "y": 125, "dept": "finance", "spot_type": "work"},
    "finance_desk_2": {"floor": 2, "x": 455, "y": 125, "dept": "finance", "spot_type": "work"},
    "finance_desk_3": {"floor": 2, "x": 506, "y": 125, "dept": "finance", "spot_type": "work"},
    "finance_desk_4": {"floor": 2, "x": 404, "y": 155, "dept": "finance", "spot_type": "work"},
    "finance_desk_5": {"floor": 2, "x": 455, "y": 155, "dept": "finance", "spot_type": "work"},
    "finance_desk_6": {"floor": 2, "x": 506, "y": 155, "dept": "finance", "spot_type": "work"},

    # ══════════════════════════════════════════
    # 2F  运营部 (office/operations)  x=370, y=200, w=170, h=140
    # ══════════════════════════════════════════
    "ops_desk_1": {"floor": 2, "x": 404, "y": 268, "dept": "operations", "spot_type": "work"},
    "ops_desk_2": {"floor": 2, "x": 455, "y": 268, "dept": "operations", "spot_type": "work"},
    "ops_desk_3": {"floor": 2, "x": 506, "y": 268, "dept": "operations", "spot_type": "work"},
    "ops_desk_4": {"floor": 2, "x": 404, "y": 301, "dept": "operations", "spot_type": "work"},
    "ops_desk_5": {"floor": 2, "x": 455, "y": 301, "dept": "operations", "spot_type": "work"},
    "ops_desk_6": {"floor": 2, "x": 506, "y": 301, "dept": "operations", "spot_type": "work"},

    # ══════════════════════════════════════════
    # 3F  会议室 (meeting)  x=20, y=60, w=560, h=160
    # 家具：table@0.5,0.5 | chair@0.25,0.35 | chair@0.75,0.35 | chair@0.25,0.65 | chair@0.75,0.65 | screen@0.5,0.12
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
    # 3F  总监办公室 (office/management)  x=20, y=280, w=260, h=260
    # 家具 (office)：使用中央工位作为"总监座"锚点
    # ══════════════════════════════════════════
    "director_desk":      {"floor": 3, "x": 150, "y": 390, "dept": "management", "spot_type": "anchor"},
    "director_visitor_1": {"floor": 3, "x": 72,  "y": 459, "dept": "management", "spot_type": "visitor"},
    "director_visitor_2": {"floor": 3, "x": 150, "y": 459, "dept": "management", "spot_type": "visitor"},
    "director_visitor_3": {"floor": 3, "x": 228, "y": 459, "dept": "management", "spot_type": "visitor"},

    # ══════════════════════════════════════════
    # 3F  CEO办公室 (ceo_office/management)  x=320, y=280, w=260, h=260
    # 家具：desk@0.5,0.35 | bookshelf*2 | sofa@0.3,0.75 | plant
    # ══════════════════════════════════════════
    "ceo_desk":      {"floor": 3, "x": 450, "y": 390, "dept": "management", "spot_type": "anchor"},
    "ceo_sofa":      {"floor": 3, "x": 398, "y": 482, "dept": "management", "spot_type": "visitor"},
    "ceo_visitor_1": {"floor": 3, "x": 450, "y": 482, "dept": "management", "spot_type": "visitor"},
    "ceo_visitor_2": {"floor": 3, "x": 500, "y": 482, "dept": "management", "spot_type": "visitor"},
}


# ---------------------------------------------------------------------------
# 预计算编码Y坐标（避免重复计算）
# ---------------------------------------------------------------------------
for _name, _s in SPOTS.items():
    _s["encoded_y"] = _s["y"] + (_s["floor"] - 1) * FLOOR_Y_OFFSET

# ---------------------------------------------------------------------------
# 按部门/类型分组的快查表
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

# HR reception 也算大厅社交区
_LOBBY_SPOTS.append("lobby_reception")


def _decode_floor(encoded_y: int) -> int:
    floor = encoded_y // FLOOR_Y_OFFSET + 1
    return max(1, min(3, floor))


def _decode_canvas_y(encoded_y: int) -> int:
    return encoded_y % FLOOR_Y_OFFSET


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def get_spot_pos(spot_name: str) -> tuple[int, int]:
    """返回 (pos_x, encoded_pos_y) 用于直接写入 AgentProfile."""
    s = SPOTS[spot_name]
    return (s["x"], s["encoded_y"])


def get_spot_name_by_pos(pos_x: int, encoded_pos_y: int) -> str | None:
    """根据坐标反查座位名称（完全匹配）。"""
    for name, spot in SPOTS.items():
        if spot["x"] == pos_x and spot["encoded_y"] == encoded_pos_y:
            return name
    return None


def get_work_spots(department: str) -> list[str]:
    """返回指定部门的所有工位名称列表."""
    return list(_DEPT_WORK_SPOTS.get(department, []))


def assign_work_spot(department: str, agent_id: int) -> str | None:
    """
    为 agent 分配一个确定性工位（用 agent_id 取模保证同一 agent 总去同一桌）。
    如果部门没有工位定义，返回 None。
    """
    spots = _DEPT_WORK_SPOTS.get(department, [])
    if not spots:
        return None
    return spots[agent_id % len(spots)]


def assign_rest_spot(agent_id: int | None = None) -> str:
    """返回一个咖啡厅座位（可按 agent_id 确定性分配）。"""
    if agent_id is not None:
        return _REST_SPOTS[agent_id % len(_REST_SPOTS)]
    return random.choice(_REST_SPOTS)


def assign_lobby_spot(agent_id: int | None = None) -> str:
    """返回一个大厅休闲位（可按 agent_id 确定性分配）。"""
    if agent_id is not None:
        return _LOBBY_SPOTS[agent_id % len(_LOBBY_SPOTS)]
    return random.choice(_LOBBY_SPOTS)


def assign_meeting_spot(agent_id: int | None = None) -> str:
    """返回一个会议室座椅（如提供 agent_id 则确定性分配）."""
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
    返回高管的锚点座位名称。
    仅管理线角色可使用高管锚点：
    - CEO (level>=6) → ceo_desk
    - 总监 (level==5) → director_desk
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
    """判断是否为常驻高管（仅管理线 level>=5）。"""
    return career_level >= 5 and _is_management_track(department, career_path)


def get_visitor_spots(career_level: int) -> list[str]:
    """
    返回拜访对应级别高管时可坐的访客席列表。
    向CEO汇报 → CEO办公室访客席；向总监汇报 → 总监办公室访客席。
    """
    if career_level >= 6:
        return ["ceo_sofa", "ceo_visitor_1", "ceo_visitor_2"]
    if career_level == 5:
        return ["director_visitor_1", "director_visitor_2", "director_visitor_3"]
    return []


def spot_to_room_name(spot_name: str) -> str:
    """将座位名映射为中文房间名，用于日志和记忆内容."""
    if spot_name.startswith("lobby_"):
        return "大厅"
    if spot_name.startswith("cafe_"):
        return "咖啡厅"
    if spot_name.startswith("hr_"):
        return "HR部门"
    if spot_name.startswith("eng_"):
        return "工程部"
    if spot_name.startswith("marketing_"):
        return "市场部"
    if spot_name.startswith("product_"):
        return "产品部"
    if spot_name.startswith("finance_"):
        return "财务部"
    if spot_name.startswith("ops_"):
        return "运营部"
    if spot_name.startswith("meeting_"):
        return "会议室"
    if spot_name.startswith("director_"):
        return "总监办公室"
    if spot_name.startswith("ceo_"):
        return "CEO办公室"
    return spot_name


def get_movable_spot_names(
    career_level: int,
    department: str | None = None,
    career_path: str | None = None,
) -> list[str]:
    """
    返回该角色允许停留的座位集合。
    - 默认：所有非锚点位
    - 高管：额外允许自己的锚点
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
    将任意坐标吸附到最近的合法语义座位。
    优先在目标楼层内吸附；若目标楼层无候选，再回退全局。
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
    根据任务语义分配目标座位，保证人物落在有意义点位。
    """
    if is_anchor_role(career_level, department, career_path):
        anchor = get_anchor_spot(career_level, department, career_path)
        if anchor:
            return anchor

    text = ((task_type or "") + " " + (task_title or "")).lower()
    meeting_keywords = ("meeting", "sync", "review", "汇报", "会议", "评审", "复盘", "培训")
    hr_keywords = ("interview", "recruit", "hire", "onboard", "招聘", "面试", "入职")
    social_keywords = ("social", "collab", "沟通", "协作", "社交", "团建")
    rest_keywords = ("break", "lunch", "coffee", "休息", "午餐", "茶歇")

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
    下班后的停留点位分配。
    为避免所有人堆叠在同一点，并保持多楼层可见性：
    - 高管优先回自己的锚点办公室；
    - 普通员工按 agent_id 在“部门工位 / 大厅 / 咖啡厅”三类点位确定性分散。
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
