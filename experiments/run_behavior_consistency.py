import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.engine.agent_ai import _get_mbti_weights

from experiments.utils import (
    ACTIONS,
    MBTI_TYPES,
    environment_metadata,
    l1_distance,
    normalize,
    sample_distribution,
    write_csv,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MBTI behavior consistency simulation.")
    parser.add_argument("--ticks", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="results/behavior_consistency.csv")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    rows = []
    scores = []

    for mbti in MBTI_TYPES:
        expected = normalize(_get_mbti_weights(mbti))
        observed = sample_distribution(expected, args.ticks, rng)
        score = 1.0 - 0.5 * l1_distance(observed, expected)
        scores.append(score)
        rows.append(
            {
                "mbti": mbti,
                "work_pct": round(observed["work"] * 100, 4),
                "chat_pct": round(observed["chat"] * 100, 4),
                "rest_pct": round(observed["rest"] * 100, 4),
                "move_pct": round(observed["move_to"] * 100, 4),
                "meeting_pct": round(observed["meeting"] * 100, 4),
                "expected_work_pct": round(expected["work"] * 100, 4),
                "expected_chat_pct": round(expected["chat"] * 100, 4),
                "expected_rest_pct": round(expected["rest"] * 100, 4),
                "expected_move_pct": round(expected["move_to"] * 100, 4),
                "expected_meeting_pct": round(expected["meeting"] * 100, 4),
                "consistency_score": round(score, 6),
            }
        )

    rows.append(
        {
            "mbti": "__summary__",
            "work_pct": "",
            "chat_pct": "",
            "rest_pct": "",
            "move_pct": "",
            "meeting_pct": "",
            "expected_work_pct": "",
            "expected_chat_pct": "",
            "expected_rest_pct": "",
            "expected_move_pct": "",
            "expected_meeting_pct": "",
            "consistency_score": round(sum(scores) / len(scores), 6),
        }
    )

    write_csv(
        args.output,
        rows,
        [
            "mbti",
            "work_pct",
            "chat_pct",
            "rest_pct",
            "move_pct",
            "meeting_pct",
            "expected_work_pct",
            "expected_chat_pct",
            "expected_rest_pct",
            "expected_move_pct",
            "expected_meeting_pct",
            "consistency_score",
        ],
    )

    print(
        {
            "output": args.output,
            "ticks": args.ticks,
            "seed": args.seed,
            "mean_consistency_pct": round(sum(scores) / len(scores) * 100, 2),
            "environment": environment_metadata(),
        }
    )


if __name__ == "__main__":
    main()
