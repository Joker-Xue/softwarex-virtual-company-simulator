"""
MBTI PersonalityCompatibleSexEngine - Relationship Dynamics (C-17)

Calculate the compatibility scores between two personality types based on MBTI theory。
"""

# All 16 MBTItypes
MBTI_TYPES = [
    "INTJ", "INTP", "ENTJ", "ENTP",
    "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ",
    "ISTP", "ISFP", "ESTP", "ESFP",
]

# Highly compatible pairing (0.85-1.0) - complementary type
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

# Low compatible pairing (0.20-0.49) - conflict type
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

# MBTI: Mediumcompatible within the same group
MBTI_GROUPS = {
    "NT": {"INTJ", "INTP", "ENTJ", "ENTP"},     # analyze home
    "NF": {"INFJ", "INFP", "ENFJ", "ENFP"},      # diplomat
    "SJ": {"ISTJ", "ISFJ", "ESTJ", "ESFJ"},      # Defender
    "SP": {"ISTP", "ISFP", "ESTP", "ESFP"},       # explorer
}

# Relationship Advice Template
COMPATIBILITY_TIPS: dict[str, list[str]] = {
    "excellent": [
        "You are a natural complement to each other，Efficient communication and good understanding。",
        "In project cooperation，You complement each other's shortcomings very well.",
        "It is recommended to arrange more collaboration tasks，Play 1+1>2 effects。",
    ],
    "good": [
        "Your cooperation base is good，have more in common。",
        "Cooperate smoothly in Same type projects，Suitable for being teammates in the same group。",
        "It is recommended to deepen understanding through communication，Further enhance tacit understanding。",
    ],
    "generally": [
        "There are certain differences in your thinking patterns，Need more communication。",
        "When cooperating, pay attention to transposition Thinking，Respect each other's way of working。",
        "Recommended to increase interaction in non-emergency projects，Gradually break in。",
    ],
    "lower": [
        "Your personalities are quite different，prone to friction。",
        "When collaborating, special attention needs to be paid to communication methods，avoid conflict。",
        "It is recommended to enhance understanding through mentorship or Team BuildingActivity.",
    ],
}


def _get_group(mbti: str) -> str | None:
    """Get the group to which MBTItype belongs"""
    for group_name, members in MBTI_GROUPS.items():
        if mbti in members:
            return group_name
    return None


def _count_shared_dimensions(mbti_a: str, mbti_b: str) -> int:
    """Calculate the number of dimensions shared by two MBTI types (0-4)"""
    return sum(1 for a, b in zip(mbti_a, mbti_b) if a == b)


def get_compatibility(mbti_a: str, mbti_b: str) -> float:
    """
    Calculate the compatibility scores of two MBTI types。

    Args:
        mbti_a: The first MBTI type (like "INTJ")
        mbti_b: Second MBTI type (like "ENTP")

    Returns:
        0.0 1.0 Compatibility score between
    """
    mbti_a = mbti_a.upper().strip()
    mbti_b = mbti_b.upper().strip()

    # Same type
    if mbti_a == mbti_b:
        return 0.75

    # Check for high-compatibility pairings
    pair = frozenset({mbti_a, mbti_b})
    if pair in HIGH_COMPAT_PAIRS:
        return HIGH_COMPAT_PAIRS[pair]

    # Check for low-compatibility pairings
    if pair in LOW_COMPAT_PAIRS:
        return LOW_COMPAT_PAIRS[pair]

    # In the same group: Mediumcompatible，Fine-tune based on shared dimensions
    group_a = _get_group(mbti_a)
    group_b = _get_group(mbti_b)
    shared = _count_shared_dimensions(mbti_a, mbti_b)

    if group_a == group_b and group_a is not None:
        # Within the same group: 0.60 - 0.80 based on shared dimensions
        return 0.55 + shared * 0.07

    # Other cases: Calculated based on shared dimensions
    # 0 shares: 0.45, 1indivual: 0.52, 2indivual: 0.59, 3indivual: 0.66
    return 0.40 + shared * 0.08


def get_compatibility_label(score: float) -> str:
    """
    Back tag based on compatibility score。

    Args:
        score: 0.0 to a score of 1.0

    Returns:
        "excellent" / "good" / "generally" / "lower"
    """
    if score >= 0.85:
        return "excellent"
    elif score >= 0.60:
        return "good"
    elif score >= 0.45:
        return "generally"
    else:
        return "lower"


def get_compatibility_tips(mbti_a: str, mbti_b: str) -> str:
    """
    Back relationship recommendations based on two MBTI types。

    Args:
        mbti_a: The first MBTI type
        mbti_b: Second MBTI type

    Returns:
        relationship advice text
    """
    score = get_compatibility(mbti_a, mbti_b)
    label = get_compatibility_label(score)
    tips = COMPATIBILITY_TIPS.get(label, COMPATIBILITY_TIPS["generally"])

    # Give more detailed suggestions based on specific type combinations
    mbti_a = mbti_a.upper().strip()
    mbti_b = mbti_b.upper().strip()
    group_a = _get_group(mbti_a)
    group_b = _get_group(mbti_b)

    base_tip = tips[0]

    # Additional details
    if group_a == "NT" and group_b == "NF":
        base_tip += " The combination of rational analysis and Feeling insights can produce a unique perspective。"
    elif group_a == "NF" and group_b == "NT":
        base_tip += " FeelingThe combination of insight and rational analysis creates a unique perspective。"
    elif group_a == "SJ" and group_b == "SP":
        base_tip += " The combination of solid execution and flexibility is valuable in a team。"
    elif group_a == "SP" and group_b == "SJ":
        base_tip += " The combination of flexibility and solid execution is valuable in a team。"
    elif group_a == "NT" and group_b == "SJ":
        base_tip += " The combination of strategic thinking and detailed execution can ensure the implementation of the plan。"
    elif group_a == "SJ" and group_b == "NT":
        base_tip += " The combination of detailed execution and strategic thinking can ensure the implementation of the plan."
    elif group_a == "NF" and group_b == "SP":
        base_tip += " The collision of idealism and pragmatism can inspire innovation。"
    elif group_a == "SP" and group_b == "NF":
        base_tip += " The collision of pragmatism and idealism can inspire innovation。"

    return base_tip
