import csv
import json
import math
import os
import platform
import random
import sys
from datetime import datetime, timezone
from itertools import combinations

MBTI_TYPES = [a + b + c + d for a in "EI" for b in "SN" for c in "TF" for d in "JP"]
ACTIONS = ["work", "chat", "rest", "move_to", "meeting"]
BASE_WEIGHTS = {"work": 30, "chat": 20, "rest": 15, "move_to": 25, "meeting": 10}


def ensure_parent(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.get(action, 0.0) for action in ACTIONS)
    if total <= 0:
        return {action: 0.0 for action in ACTIONS}
    return {action: weights.get(action, 0.0) / total for action in ACTIONS}


def l1_distance(p: dict[str, float], q: dict[str, float]) -> float:
    return sum(abs(p.get(action, 0.0) - q.get(action, 0.0)) for action in ACTIONS)


def kl_divergence(p: dict[str, float], q: dict[str, float], eps: float = 1e-12) -> float:
    total = 0.0
    for action in ACTIONS:
        pa = p.get(action, 0.0) + eps
        qa = q.get(action, 0.0) + eps
        total += pa * math.log(pa / qa)
    return total


def shannon_entropy(p: dict[str, float], eps: float = 1e-12) -> float:
    total = 0.0
    for action in ACTIONS:
        pa = p.get(action, 0.0)
        if pa > 0:
            total -= pa * math.log(pa + eps)
    return total


def mean_pairwise_kl(distributions: dict[str, dict[str, float]]) -> float:
    values = [
        kl_divergence(distributions[a], distributions[b])
        for a, b in combinations(distributions.keys(), 2)
    ]
    return sum(values) / len(values) if values else 0.0


def sample_distribution(
    probs: dict[str, float],
    trials: int,
    rng: random.Random,
    force_action: str | None = None,
) -> dict[str, float]:
    counts = {action: 0 for action in ACTIONS}
    if force_action is not None:
        counts[force_action] = trials
        return {action: counts[action] / trials for action in ACTIONS}
    actions = rng.choices(ACTIONS, weights=[probs[action] for action in ACTIONS], k=trials)
    for action in actions:
        counts[action] += 1
    return {action: counts[action] / trials for action in ACTIONS}


def write_csv(path: str, rows: list[dict], fieldnames: list[str]) -> None:
    ensure_parent(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: str, payload: dict) -> None:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def environment_metadata() -> dict:
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
    }
