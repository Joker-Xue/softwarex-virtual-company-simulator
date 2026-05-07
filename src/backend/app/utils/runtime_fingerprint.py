"""
Running Behavior fingerprint tool.

Used to confirm which version of virtual is loaded by the Current process companyBehaviorLogic，
Avoid misjudgments caused by "the code has been changed but the service is still running the old process".
"""

from __future__ import annotations

import hashlib
import inspect
from typing import Any

from app.engine import named_spots, npc_seeder


NPC_BEHAVIOR_RULE_VERSION = "npc-behavior-v3"
AFTER_WORK_POLICY_VERSION = "after-work-deterministic-v2"
ANCHOR_POLICY_VERSION = "anchor-management-only-v2"


def _hash_source(obj: Any) -> str:
    src = inspect.getsource(obj)
    return hashlib.sha256(src.encode("utf-8")).hexdigest()[:12]


def get_runtime_fingerprint() -> dict:
    """
    BackKey function source code summary and strategy version number。
    """
    parts = {
        "get_anchor_spot": _hash_source(named_spots.get_anchor_spot),
        "get_after_work_spot": _hash_source(named_spots.get_after_work_spot),
        "get_task_target_spot": _hash_source(named_spots.get_task_target_spot),
        "reset_npc_positions": _hash_source(npc_seeder.reset_npc_positions),
        "rebuild_npcs": _hash_source(npc_seeder.rebuild_npcs),
    }
    compact = "|".join(f"{k}:{v}" for k, v in sorted(parts.items()))
    digest = hashlib.sha256(compact.encode("utf-8")).hexdigest()[:16]
    return {
        "fingerprint": digest,
        "parts": parts,
        "behavior_versions": {
            "npc_behavior_rule": NPC_BEHAVIOR_RULE_VERSION,
            "after_work_policy": AFTER_WORK_POLICY_VERSION,
            "anchor_policy": ANCHOR_POLICY_VERSION,
        },
    }
