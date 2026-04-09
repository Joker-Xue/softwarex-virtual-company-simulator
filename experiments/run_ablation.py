import argparse
import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.engine.agent_ai import _get_mbti_weights
from app.engine.event_engine import should_join_event

from experiments.utils import (
    ACTIONS,
    BASE_WEIGHTS,
    MBTI_TYPES,
    environment_metadata,
    mean_pairwise_kl,
    normalize,
    shannon_entropy,
    write_csv,
)


@dataclass
class DummyAgent:
    mbti: str
    current_action: str = "idle"
    attr_communication: int = 68
    attr_technical: int = 68


@dataclass
class DummyEvent:
    name: str
    event_type: str


EVENT_POOL = [
    DummyEvent("Tech talk", "tech_talk"),
    DummyEvent("Skills workshop", "training"),
    DummyEvent("Team building", "team_building"),
    DummyEvent("Welcome meetup", "welcome"),
    DummyEvent("Department award", "dept_award"),
    DummyEvent("Emergency mobilization", "emergency"),
]


def event_action(event: DummyEvent) -> str:
    if event.event_type in {"team_building", "welcome", "dept_award"}:
        return "chat"
    if event.event_type in {"emergency"}:
        return "work"
    return "meeting"


def simulate_distribution(
    mbti: str,
    trials: int,
    rng: random.Random,
    use_mbti: bool,
    use_events: bool,
    event_probability: float,
    event_persistence: int,
) -> dict[str, float]:
    base = _get_mbti_weights(mbti) if use_mbti else dict(BASE_WEIGHTS)
    probs = normalize(base)
    counts = {action: 0 for action in ACTIONS}
    agent = DummyAgent(mbti=mbti)
    event_cooldown = 0
    persisted_event_action = "meeting"

    for _ in range(trials):
        action = None
        if use_events and event_cooldown > 0:
            action = persisted_event_action
            event_cooldown -= 1
        elif use_events and rng.random() < event_probability:
            event = rng.choice(EVENT_POOL)
            joined, _, _ = should_join_event(agent, event)
            if joined:
                action = event_action(event)
                persisted_event_action = action
                event_cooldown = max(0, event_persistence - 1)
        if action is None:
            action = rng.choices(ACTIONS, weights=[probs[a] for a in ACTIONS], k=1)[0]
        agent.current_action = action
        counts[action] += 1

    return {action: counts[action] / trials for action in ACTIONS}


def summarize(distributions: dict[str, dict[str, float]]) -> tuple[float, float]:
    entropy = sum(shannon_entropy(dist) for dist in distributions.values()) / len(distributions)
    mean_kl = mean_pairwise_kl(distributions)
    return entropy, mean_kl


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ablation simulations.")
    parser.add_argument("--trials", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--condition", choices=["full", "no_mbti", "no_event", "all"], default="all")
    parser.add_argument("--event-probability", type=float, default=0.25)
    parser.add_argument("--event-persistence", type=int, default=2)
    parser.add_argument("--output", default="results/ablation.csv")
    args = parser.parse_args()

    conditions = ["full", "no_mbti", "no_event"] if args.condition == "all" else [args.condition]
    rows = []
    summary = {}

    for condition in conditions:
        use_mbti = condition != "no_mbti"
        use_events = condition != "no_event"
        rng = random.Random(args.seed)
        distributions = {
            mbti: simulate_distribution(
                mbti,
                args.trials,
                rng,
                use_mbti=use_mbti,
                use_events=use_events,
                event_probability=args.event_probability,
                event_persistence=args.event_persistence,
            )
            for mbti in MBTI_TYPES
        }
        mean_entropy, mean_kl = summarize(distributions)
        summary[condition] = {
            "mean_entropy": mean_entropy,
            "mean_kl_divergence": mean_kl,
        }
        rows.append(
            {
                "condition": condition,
                "mean_entropy": round(mean_entropy, 6),
                "mean_kl_divergence": round(mean_kl, 6),
                "distinctiveness_reduction_pct": "",
                "entropy_drop_pct": "",
            }
        )

    if "full" in summary and "no_mbti" in summary:
        reduction = (1.0 - summary["no_mbti"]["mean_kl_divergence"] / summary["full"]["mean_kl_divergence"]) * 100
        for row in rows:
            if row["condition"] == "no_mbti":
                row["distinctiveness_reduction_pct"] = round(reduction, 2)

    if "full" in summary and "no_event" in summary:
        drop = (1.0 - summary["no_event"]["mean_entropy"] / summary["full"]["mean_entropy"]) * 100
        for row in rows:
            if row["condition"] == "no_event":
                row["entropy_drop_pct"] = round(drop, 2)

    write_csv(
        args.output,
        rows,
        [
            "condition",
            "mean_entropy",
            "mean_kl_divergence",
            "distinctiveness_reduction_pct",
            "entropy_drop_pct",
        ],
    )
    print(
        {
            "output": args.output,
            "seed": args.seed,
            "trials": args.trials,
            "event_probability": args.event_probability,
            "event_persistence": args.event_persistence,
            "rows": rows,
            "environment": environment_metadata(),
        }
    )


if __name__ == "__main__":
    main()
