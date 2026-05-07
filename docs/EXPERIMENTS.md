# Experiment Reproduction Guide

This document describes the formal experiment scripts bundled with the SoftwareX virtual-company simulator artifact.

## Reproduction Rules

- Fixed seed: `42`
- Default output directory: `results/`
- Canonical execution root: repository root
- Recommended environment: the same Python and database stack used for the simulator demo

## Experiment Commands

### 1. Behavior Consistency

```bash
python experiments/run_behavior_consistency.py --ticks 1000 --seed 42 --output results/behavior_consistency.csv
```

Expected output fields:

- `mbti`
- observed action percentages
- expected action percentages
- `consistency_score`

Current baseline:

- mean consistency: `98.0%`

### 2. Ablation

```bash
python experiments/run_ablation.py --condition all --trials 1000 --seed 42 --output results/ablation.csv
```

Expected rows:

- `full`
- `no_mbti`
- `no_event`

Current baseline:

- `full.mean_kl_divergence = 0.05693`
- `no_mbti.distinctiveness_reduction_pct = 65.33`
- `no_event.entropy_drop_pct = 1.78`

### 3. Tick Benchmark

```bash
python experiments/run_tick_benchmark.py --warmup 10 --ticks 50 --output results/tick_benchmark.json
```

Expected fields:

- `mean_ms`
- `median_ms`
- `p95_ms`
- `min_ms`
- `max_ms`

Current baseline:

- `mean_ms = 129.08`
- `median_ms = 118.55`
- `p95_ms = 160.18`

### 4. Availability Probe

```bash
python experiments/run_availability_probe.py --duration-seconds 60 --output results/availability.json
```

Expected fields:

- `probe_total`
- `probe_success`
- `probe_fail`
- `availability_pct`

Current baseline:

- `probe_total = 29976`
- `probe_success = 29976`
- `availability_pct = 100.0`

## Accepted Rerun Tolerance

- Behavior consistency and ablation should remain structurally similar under the fixed seed and code version.
- Tick benchmark is environment-sensitive. Small runtime drift is acceptable as long as the JSON schema is intact and no repeated failures occur.
- Availability should remain near `100%` in ASGI mode for the local probe unless the stack is being modified concurrently.

## Output Files

- `results/behavior_consistency.csv`
- `results/ablation.csv`
- `results/tick_benchmark.json`
- `results/availability.json`

## Notes

- Avoid running the tick benchmark and availability probe against the same mutable database state in parallel during verification, because concurrent simulator activity can introduce noisy latency or deadlock artifacts.
- If simulator-core behavior changes, regenerate the baseline outputs before publishing the public SoftwareX repository.
