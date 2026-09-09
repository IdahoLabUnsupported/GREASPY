#!/usr/bin/env python3
# Copyright 2026, Battelle Energy Alliance, LLC. All Rights Reserved.
"""
Batch-generate randomized spectrum files using GREASPY tools.

This script reuses GREASPY_random_spectrum helpers and produces a folder of files.
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import random
from pathlib import Path
from typing import Dict, List, Tuple

from GREASPY import CalcInputs, GreaseDataModel, SHIELDING_MATERIALS
from GREASPY_export import (
    SUPPORTED_SPECTRUM_FORMATS,
    extension_for_format,
    write_spectrum_file,
)
from GREASPY_random_spectrum import build_default_filename


def sample_activity(rng: random.Random, low: float, high: float, space: str) -> float:
    if space == "linear":
        return rng.uniform(low, high)
    return 10.0 ** rng.uniform(math.log10(low), math.log10(high))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a batch of randomized GREASPY spectrum files into one folder."
    )
    parser.add_argument("--count", type=int, default=100, help="Number of spectrum files to generate.")
    parser.add_argument("--outdir", type=str, default=None, help="Output directory for spectrum files.")
    parser.add_argument(
        "--format",
        choices=SUPPORTED_SPECTRUM_FORMATS,
        default="spe",
        help="Output spectrum format.",
    )
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

    model = GreaseDataModel()
    all_isotopes = model.isotope_names()

    max_iso = min(args.max_isotopes, len(all_isotopes))
    min_iso = min(args.min_isotopes, max_iso)
    if max_iso < 1:
        raise ValueError("No isotopes available in the validated GREASPY data catalog.")

    if args.outdir:
        outdir = Path(args.outdir).expanduser().resolve()
    else:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        outdir = (Path.cwd() / f"greaspy_batch_{stamp}").resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"Data catalog: {model.data_path}")
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

        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = build_default_filename(
            isotopes,
            include_bg,
            shielding_cm,
            f"{ts}_{i:06d}",
            extension=extension_for_format(args.format),
        )
        outpath = outdir / name
        write_spectrum_file(outpath, inp, res, args.format)

        if i == 1 or i % 10 == 0 or i == args.count:
            print(f"[{i}/{args.count}] {outpath.name}")

    print("Done.")


if __name__ == "__main__":
    main()
