import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app

from experiments.utils import environment_metadata, write_json


async def main_async(args) -> dict:
    paths = ["/openapi.json", "/api/simulation/status", "/api/simulation/diagnostics"]
    total = 0
    success = 0
    failures = []
    start = time.time()
    end_time = start + args.duration_seconds if args.duration_seconds > 0 else None

    if args.base_url:
        client = AsyncClient(base_url=args.base_url)
    else:
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test")

    async with client:
        rounds_done = 0
        while True:
            for path in paths:
                total += 1
                try:
                    response = await client.get(path, timeout=args.timeout)
                    if response.status_code < 500:
                        success += 1
                    else:
                        failures.append({"path": path, "status": response.status_code})
                except Exception as exc:
                    failures.append({"path": path, "error": str(exc)})
            rounds_done += 1
            if end_time is not None:
                if time.time() >= end_time:
                    break
            elif rounds_done >= args.rounds:
                break
            if args.interval > 0:
                await asyncio.sleep(args.interval)

    payload = {
        "environment": environment_metadata(),
        "mode": "http" if args.base_url else "asgi",
        "base_url": args.base_url or "http://test",
        "rounds": rounds_done,
        "duration_seconds": args.duration_seconds,
        "paths": paths,
        "probe_total": total,
        "probe_success": success,
        "probe_fail": total - success,
        "availability_pct": round(success / total * 100, 2) if total else 0.0,
        "elapsed_seconds": round(time.time() - start, 2),
        "failure_breakdown": failures[:20],
    }
    write_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run availability probes against the ASGI app or a live base URL.")
    parser.add_argument("--rounds", type=int, default=60)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--interval", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--output", default="results/availability.json")
    args = parser.parse_args()
    payload = asyncio.run(main_async(args))
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
