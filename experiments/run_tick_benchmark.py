import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import init_db
from app.engine.npc_seeder import seed_npcs_standalone
from app.engine.simulation_loop import simulation_tick

from experiments.utils import environment_metadata, write_json


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    idx = (len(ordered) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


async def main_async(args) -> dict:
    await init_db()
    await seed_npcs_standalone()

    try:
        import app.engine.channel_engine as channel_engine

        async def _noop(*_args, **_kwargs):
            return None

        channel_engine.post_department_chatter = _noop
        channel_engine.post_daily_announcement = _noop
    except Exception:
        pass

    warmup = []
    for _ in range(args.warmup):
        t0 = time.perf_counter()
        await simulation_tick()
        warmup.append((time.perf_counter() - t0) * 1000)

    durations = []
    for _ in range(args.ticks):
        t0 = time.perf_counter()
        await simulation_tick()
        durations.append((time.perf_counter() - t0) * 1000)

    payload = {
        "environment": environment_metadata(),
        "warmup_count": args.warmup,
        "tick_count": args.ticks,
        "warmup_mean_ms": round(statistics.mean(warmup), 2) if warmup else 0.0,
        "mean_ms": round(statistics.mean(durations), 2),
        "median_ms": round(statistics.median(durations), 2),
        "p95_ms": round(percentile(durations, 0.95), 2),
        "min_ms": round(min(durations), 2),
        "max_ms": round(max(durations), 2),
    }
    write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark simulation tick latency.")
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--ticks", type=int, default=100)
    parser.add_argument("--output", default="results/tick_benchmark.json")
    args = parser.parse_args()
    payload = asyncio.run(main_async(args))
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
