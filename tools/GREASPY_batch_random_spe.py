#!/usr/bin/env python3
"""
Batch-generate randomized SPE files using GREASPY tools.

This script reuses GREASPY_random_spe helpers and produces a folder of files.
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import random
from pathlib import Path
from typing import Dict, List, Tuple

from GREASPY import CalcInputs, GreaseDataModel, SHIELDING_MATERIALS
from GREASPY_random_spe import build_default_filename, build_spe_lines, resolve_workbook


def sample_activity(rng: random.Random, low: float, high: float, space: str) -> float:
    if space == "linear":
        return rng.uniform(low, high)
    return 10.0 ** rng.uniform(math.log10(low), math.log10(high))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a batch of randomized GREASPY SPE files into one folder."
    )
    parser.add_argument("--count", type=int, default=100, help="Number of SPE files to generate.")
    parser.add_argument("--workbook", type=str, default=None, help="Optional workbook path.")
    parser.add_argument("--outdir", type=str, default=None, help="Output directory for SPE files.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")

    parser.add_argument("--min-isotopes", type=int, default=1, help="Minimum isotopes per file.")
    parser.add_argument("--max-isotopes", type=int, default=10, help="Maximum isotopes per file.")
    parser.add_argument(
        "--activity-min",
        type=float,
        default=1e-12,
        help="Minimum activity in Ci.",
    )
    parser.add_argument(
        "--activity-max",
        type=float,
        default=1e-3,
        help="Maximum activity in Ci.",
    )
    parser.add_argument(
        "--activity-space",
        choices=["log", "linear"],
        default="log",
        help="Sampling space for activity values.",
    )

    parser.add_argument(
        "--count-time-min",
        type=float,
        default=10.0,
        help="Minimum live counting time in seconds.",
    )
    parser.add_argument(
        "--count-time-max",
        type=float,
        default=3600.0,
        help="Maximum live counting time in seconds.",
    )
    parser.add_argument(
        "--distance-min-cm",
        type=float,
        default=0.0,
        help="Minimum counting distance in cm.",
    )
    parser.add_argument(
        "--distance-max-cm",
        type=float,
        default=20.0,
        help="Maximum counting distance in cm.",
    )

    parser.add_argument(
        "--shield-max-cm",
        type=float,
        default=5.0,
        help="Maximum uniform shield thickness (minimum is fixed at 0.0 cm).",
    )

    args = parser.parse_args()

    if args.count <= 0:
        raise ValueError("--count must be > 0")
    if args.min_isotopes < 1:
        raise ValueError("--min-isotopes must be >= 1")
    if args.max_isotopes < args.min_isotopes:
        raise ValueError("--max-isotopes must be >= --min-isotopes")
    if args.max_isotopes > 10:
        raise ValueError("--max-isotopes cannot exceed 10")
    if args.activity_min <= 0 or args.activity_max <= 0:
        raise ValueError("Activity bounds must be > 0")
    if args.activity_max < args.activity_min:
        raise ValueError("--activity-max must be >= --activity-min")
    if args.shield_max_cm < 0:
        raise ValueError("--shield-max-cm must be >= 0")
    if args.count_time_min <= 0 or args.count_time_max <= 0:
        raise ValueError("Count-time bounds must be > 0")
    if args.count_time_max < args.count_time_min:
        raise ValueError("--count-time-max must be >= --count-time-min")
    if args.distance_min_cm < 0 or args.distance_max_cm < 0:
        raise ValueError("Distance bounds must be >= 0")
    if args.distance_max_cm < args.distance_min_cm:
        raise ValueError("--distance-max-cm must be >= --distance-min-cm")

    rng = random.Random(args.seed)

    workbook = resolve_workbook(args.workbook)
    model = GreaseDataModel(workbook)
    all_isotopes = model.isotope_names()

    max_iso = min(args.max_isotopes, len(all_isotopes))
    min_iso = min(args.min_isotopes, max_iso)
    if max_iso < 1:
        raise ValueError("No isotopes available in workbook.")

    if args.outdir:
        outdir = Path(args.outdir).expanduser().resolve()
    else:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outdir = (Path.cwd() / f"greaspy_batch_{stamp}").resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"Workbook: {workbook}")
    print(f"Output dir: {outdir}")
    print(f"Generating {args.count} files...")

    for i in range(1, args.count + 1):
        n_isotopes = rng.randint(min_iso, max_iso)
        chosen = rng.sample(all_isotopes, n_isotopes)

        isotopes: List[Tuple[str, float]] = []
        for name in chosen:
            act = sample_activity(rng, args.activity_min, args.activity_max, args.activity_space)
            isotopes.append((name, act))

        include_bg = rng.choice([True, False])

        shielding_cm: Dict[str, float] = {m: 0.0 for m in SHIELDING_MATERIALS}
        if model.has_shielding:
            for m in SHIELDING_MATERIALS:
                shielding_cm[m] = rng.uniform(0.0, args.shield_max_cm)

        count_time_sec = rng.uniform(args.count_time_min, args.count_time_max)
        distance_cm = max(rng.uniform(args.distance_min_cm, args.distance_max_cm), 1e-12)

        inp = CalcInputs(
            isotopes=isotopes,
            count_time_sec=count_time_sec,
            distance_cm=distance_cm,
            include_background=include_bg,
            shielding_cm=shielding_cm,
        )
        res = model.compute(inp)
        lines = build_spe_lines(inp, res)

        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = build_default_filename(isotopes, include_bg, shielding_cm, f"{ts}_{i:06d}")
        outpath = outdir / name
        outpath.write_text("\n".join(lines) + "\n", encoding="utf-8")

        if i == 1 or i % 10 == 0 or i == args.count:
            print(f"[{i}/{args.count}] {outpath.name}")

    print("Done.")


if __name__ == "__main__":
    main()
