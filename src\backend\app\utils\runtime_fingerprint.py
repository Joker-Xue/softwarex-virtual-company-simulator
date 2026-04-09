"""
运行态行为指纹工具。

用于确认当前进程加载的是哪一版虚拟公司行为逻辑，
避免“代码已改但服务仍跑旧进程”造成误判。
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
    返回关键函数源码摘要与策略版本号。
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
