"""
MBTI 性格兼容性引擎 - 关系动力学 (C-17)

基于MBTI理论计算两种性格类型之间的兼容性分数。
"""

# 所有16种MBTI类型
MBTI_TYPES = [
    "INTJ", "INTP", "ENTJ", "ENTP",
    "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ",
    "ISTP", "ISFP", "ESTP", "ESFP",
]

# 高兼容性配对 (0.85-1.0) - 互补类型
HIGH_COMPAT_PAIRS: dict[frozenset[str], float] = {
    frozenset({"INTJ", "ENTP"}): 0.95,
    frozenset({"INTJ", "ENFP"}): 0.90,
    frozenset({"INTP", "ENTJ"}): 0.92,
    frozenset({"INTP", "ENFJ"}): 0.88,
    frozenset({"INFJ", "ENFP"}): 0.95,
    frozenset({"INFJ", "ENTP"}): 0.90,
    frozenset({"INFP", "ENFJ"}): 0.93,
    frozenset({"INFP", "ENTJ"}): 0.85,
    frozenset({"ISTJ", "ESFP"}): 0.90,
    frozenset({"ISTJ", "ESTP"}): 0.85,
    frozenset({"ISFJ", "ESTP"}): 0.90,
    frozenset({"ISFJ", "ESFP"}): 0.88,
    frozenset({"ESTJ", "ISFP"}): 0.88,
    frozenset({"ESTJ", "ISTP"}): 0.85,
    frozenset({"ESFJ", "ISTP"}): 0.88,
    frozenset({"ESFJ", "ISFP"}): 0.90,
    frozenset({"ENTJ", "INFP"}): 0.85,
    frozenset({"ENTJ", "INFJ"}): 0.87,
    frozenset({"ENFJ", "INFP"}): 0.93,
    frozenset({"ENFJ", "ISTP"}): 0.85,
    frozenset({"ENFP", "INTJ"}): 0.90,
    frozenset({"ENFP", "INFJ"}): 0.95,
    frozenset({"ENTP", "INFJ"}): 0.90,
    frozenset({"ENTP", "INTJ"}): 0.95,
    frozenset({"ESTP", "ISFJ"}): 0.90,
    frozenset({"ESFP", "ISTJ"}): 0.90,
}

# 低兼容性配对 (0.20-0.49) - 冲突类型
LOW_COMPAT_PAIRS: dict[frozenset[str], float] = {
    frozenset({"INTJ", "ESFP"}): 0.35,
    frozenset({"INTJ", "ESFJ"}): 0.40,
    frozenset({"INTP", "ESFJ"}): 0.30,
    frozenset({"INTP", "ESFP"}): 0.38,
    frozenset({"INFJ", "ESTP"}): 0.35,
    frozenset({"INFJ", "ESTJ"}): 0.42,
    frozenset({"INFP", "ESTP"}): 0.28,
    frozenset({"INFP", "ESTJ"}): 0.32,
    frozenset({"ISTJ", "ENFP"}): 0.40,
    frozenset({"ISTJ", "ENFJ"}): 0.45,
    frozenset({"ISFJ", "ENTP"}): 0.38,
    frozenset({"ISFJ", "ENTJ"}): 0.42,
    frozenset({"ESTJ", "INFP"}): 0.32,
    frozenset({"ESFJ", "INTP"}): 0.30,
    frozenset({"ESTP", "INFP"}): 0.28,
    frozenset({"ESFP", "INTJ"}): 0.35,
}

# MBTI分组: 同组内为中等兼容性
MBTI_GROUPS = {
    "NT": {"INTJ", "INTP", "ENTJ", "ENTP"},     # 分析家
    "NF": {"INFJ", "INFP", "ENFJ", "ENFP"},      # 外交家
    "SJ": {"ISTJ", "ISFJ", "ESTJ", "ESFJ"},      # 守卫者
    "SP": {"ISTP", "ISFP", "ESTP", "ESFP"},       # 探索者
}

# 关系建议模板
COMPATIBILITY_TIPS: dict[str, list[str]] = {
    "极佳": [
        "你们是天生的互补搭档，沟通高效且默契十足。",
        "在项目合作中，你们能很好地弥补彼此的不足。",
        "建议多安排协作任务，发挥1+1>2的效果。",
    ],
    "良好": [
        "你们的合作基础不错，有较多共同点。",
        "在同类型项目中配合顺畅，适合做同组队友。",
        "建议通过交流加深理解，进一步提升默契。",
    ],
    "一般": [
        "你们的思维模式有一定差异，需要更多沟通。",
        "在合作时注意换位思考，尊重对方的工作方式。",
        "建议在非紧急项目中增加互动，逐步磨合。",
    ],
    "较低": [
        "你们的性格差异较大，容易产生摩擦。",
        "合作时需要特别注意沟通方式，避免冲突。",
        "建议通过导师制或团建活动增进了解。",
    ],
}


def _get_group(mbti: str) -> str | None:
    """获取MBTI类型所属分组"""
    for group_name, members in MBTI_GROUPS.items():
        if mbti in members:
            return group_name
    return None


def _count_shared_dimensions(mbti_a: str, mbti_b: str) -> int:
    """计算两个MBTI类型共享的维度数量 (0-4)"""
    return sum(1 for a, b in zip(mbti_a, mbti_b) if a == b)


def get_compatibility(mbti_a: str, mbti_b: str) -> float:
    """
    计算两个MBTI类型的兼容性分数。

    Args:
        mbti_a: 第一个MBTI类型 (如 "INTJ")
        mbti_b: 第二个MBTI类型 (如 "ENTP")

    Returns:
        0.0 到 1.0 之间的兼容性分数
    """
    mbti_a = mbti_a.upper().strip()
    mbti_b = mbti_b.upper().strip()

    # 相同类型
    if mbti_a == mbti_b:
        return 0.75

    # 检查高兼容性配对
    pair = frozenset({mbti_a, mbti_b})
    if pair in HIGH_COMPAT_PAIRS:
        return HIGH_COMPAT_PAIRS[pair]

    # 检查低兼容性配对
    if pair in LOW_COMPAT_PAIRS:
        return LOW_COMPAT_PAIRS[pair]

    # 同组: 中等兼容性，根据共享维度微调
    group_a = _get_group(mbti_a)
    group_b = _get_group(mbti_b)
    shared = _count_shared_dimensions(mbti_a, mbti_b)

    if group_a == group_b and group_a is not None:
        # 同组内: 0.60 - 0.80 基于共享维度
        return 0.55 + shared * 0.07

    # 其他情况: 根据共享维度计算
    # 0个共享: 0.45, 1个: 0.52, 2个: 0.59, 3个: 0.66
    return 0.40 + shared * 0.08


def get_compatibility_label(score: float) -> str:
    """
    根据兼容性分数返回标签。

    Args:
        score: 0.0 到 1.0 的分数

    Returns:
        "极佳" / "良好" / "一般" / "较低"
    """
    if score >= 0.85:
        return "极佳"
    elif score >= 0.60:
        return "良好"
    elif score >= 0.45:
        return "一般"
    else:
        return "较低"


def get_compatibility_tips(mbti_a: str, mbti_b: str) -> str:
    """
    根据两个MBTI类型返回关系建议。

    Args:
        mbti_a: 第一个MBTI类型
        mbti_b: 第二个MBTI类型

    Returns:
        关系建议文本
    """
    score = get_compatibility(mbti_a, mbti_b)
    label = get_compatibility_label(score)
    tips = COMPATIBILITY_TIPS.get(label, COMPATIBILITY_TIPS["一般"])

    # 根据具体类型组合给出更细化的建议
    mbti_a = mbti_a.upper().strip()
    mbti_b = mbti_b.upper().strip()
    group_a = _get_group(mbti_a)
    group_b = _get_group(mbti_b)

    base_tip = tips[0]

    # 补充细节
    if group_a == "NT" and group_b == "NF":
        base_tip += " 理性分析与情感洞察的结合能产生独特视角。"
    elif group_a == "NF" and group_b == "NT":
        base_tip += " 情感洞察与理性分析的结合能产生独特视角。"
    elif group_a == "SJ" and group_b == "SP":
        base_tip += " 稳健执行与灵活应变的组合在团队中很有价值。"
    elif group_a == "SP" and group_b == "SJ":
        base_tip += " 灵活应变与稳健执行的组合在团队中很有价值。"
    elif group_a == "NT" and group_b == "SJ":
        base_tip += " 战略思维与细节执行的搭配可以确保计划落地。"
    elif group_a == "SJ" and group_b == "NT":
        base_tip += " 细节执行与战略思维的搭配可以确保计划落地。"
    elif group_a == "NF" and group_b == "SP":
        base_tip += " 理想主义与实用主义的碰撞能激发创新。"
    elif group_a == "SP" and group_b == "NF":
        base_tip += " 实用主义与理想主义的碰撞能激发创新。"

    return base_tip
