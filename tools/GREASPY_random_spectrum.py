#!/usr/bin/env python3
# Copyright 2026, Battelle Energy Alliance, LLC. All Rights Reserved.
"""
Generate randomized spectrum files using the GREASPY calculation engine.

Examples:
  python GREASPY_random_spectrum.py
  python GREASPY_random_spectrum.py --seed 42 --output demo.spe
  python GREASPY_random_spectrum.py --format n42 --seed 42 --output demo.n42
  python GREASPY_random_spectrum.py --min-isotopes 2 --max-isotopes 5 --activity-min 1e-7 --activity-max 1e-3
  python GREASPY_random_spectrum.py --allow-isotopes Cs137,Ba137m,Co60 --background-mode off
  python GREASPY_random_spectrum.py --shield-mode on --shield-materials Pb,W --shield-min-cm 0.1 --shield-max-cm 2.0
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import random
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from GREASPY import CalcInputs, CalcResults, GreaseDataModel, SHIELDING_MATERIALS
from GREASPY_export import (
    SUPPORTED_SPECTRUM_FORMATS,
    build_spe_lines,
    ensure_format_extension,
    extension_for_format,
    write_spectrum_file,
)


def parse_csv_list(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def _safe_token(s: str) -> str:
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", ".", "(", ")", "/"):
            out.append("_")
    token = "".join(out)
    while "__" in token:
        token = token.replace("__", "_")
    return token.strip("_")


def _activity_tag(v: float) -> str:
    # compact scientific-style tag for filenames, e.g. 1p23e-06 -> 1p23e06
    s = f"{v:.2e}".replace("+", "")
    s = s.replace(".", "p").replace("-", "m")
    return s


def choose_background(mode: str, rng: random.Random) -> bool:
    if mode == "on":
        return True
    if mode == "off":
        return False
    return rng.choice([True, False])


def choose_shield_enabled(mode: str, rng: random.Random) -> bool:
    if mode == "on":
        return True
    if mode == "off":
        return False
    return rng.choice([True, False])


def random_activity(
    rng: random.Random,
    low: float,
    high: float,
    log_uniform: bool,
) -> float:
    if log_uniform:
        return 10.0 ** rng.uniform(math.log10(low), math.log10(high))
    return rng.uniform(low, high)


def build_default_filename(
    isotopes: List[Tuple[str, float]],
    include_background: bool,
    shielding_cm: Dict[str, float],
    timestamp: str,
    extension: str = "spe",
) -> str:
    bg_tag = "BGon" if include_background else "BGoff"

    iso_parts = []
    for name, act in isotopes[:3]:
        iso_parts.append(f"{_safe_token(name)}-{_activity_tag(act)}")
    if len(isotopes) > 3:
        iso_parts.append(f"plus{len(isotopes)-3}")
    iso_tag = "ISO_" + ("_".join(iso_parts) if iso_parts else "none")

    active_shields = [(m, v) for m, v in shielding_cm.items() if v > 0]
    if active_shields:
        sh_parts = [f"{_safe_token(m)}-{v:.2f}cm".replace(".", "p") for m, v in active_shields]
        shield_tag = "SH_" + "_".join(sh_parts)
    else:
        shield_tag = "SH_none"

    ext = extension.lstrip(".")
    name = f"greaspy_{bg_tag}_{iso_tag}_{shield_tag}_{timestamp}.{ext}"
    # Keep filename manageable on Windows paths.
    return name[:220]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate randomized GREASPY spectrum files."
    )
    parser.add_argument("--output", type=str, default=None, help="Output spectrum path.")
    parser.add_argument(
        "--format",
        choices=SUPPORTED_SPECTRUM_FORMATS,
        default="spe",
        help="Output format. Defaults to spe.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    parser.add_argument("--count-time", type=float, default=300.0, help="Live counting time in seconds.")
    parser.add_argument("--distance-cm", type=float, default=20.0, help="Counting distance in cm.")

    parser.add_argument("--min-isotopes", type=int, default=1, help="Minimum isotopes to include.")
    parser.add_argument("--max-isotopes", type=int, default=3, help="Maximum isotopes to include.")
    parser.add_argument(
        "--allow-isotopes",
        type=str,
        default=None,
        help="Comma-separated isotope whitelist (example: Cs137,Ba137m,Co60).",
    )
    parser.add_argument(
        "--exclude-isotopes",
        type=str,
        default=None,
        help="Comma-separated isotope blacklist.",
    )

    parser.add_argument("--activity-min", type=float, default=1e-7, help="Minimum activity in Ci.")
    parser.add_argument("--activity-max", type=float, default=1e-3, help="Maximum activity in Ci.")
    parser.add_argument(
        "--activity-distribution",
        choices=["log", "linear"],
        default="log",
        help="Random activity distribution.",
    )

    parser.add_argument(
        "--background-mode",
        choices=["random", "on", "off"],
        default="random",
        help="Background selection mode.",
    )
    parser.add_argument(
        "--shield-mode",
        choices=["random", "on", "off"],
        default="random",
        help="Shielding selection mode.",
    )
    parser.add_argument(
        "--shield-materials",
        type=str,
        default=None,
        help="Comma-separated allowed shielding materials. "
        "Valid: Polyethylene, Aluminum, Stainless Steel 316, Tungsten, Pb, Depleted Uranium (DU). "
        "Short aliases accepted: Poly, Al, SS, W, DU.",
    )
    parser.add_argument("--max-shield-materials", type=int, default=2, help="Max active shield materials.")
    parser.add_argument("--shield-min-cm", type=float, default=0.05, help="Min shield thickness when enabled.")
    parser.add_argument("--shield-max-cm", type=float, default=2.0, help="Max shield thickness when enabled.")

    args = parser.parse_args()

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
    if args.shield_min_cm < 0 or args.shield_max_cm < 0:
        raise ValueError("Shield thickness bounds must be >= 0")
    if args.shield_max_cm < args.shield_min_cm:
        raise ValueError("--shield-max-cm must be >= --shield-min-cm")
    if args.max_shield_materials < 0:
        raise ValueError("--max-shield-materials must be >= 0")

    rng = random.Random(args.seed)
    model = GreaseDataModel()

    all_isotopes = model.isotope_names()
    allowed = set(all_isotopes)

    if args.allow_isotopes:
        whitelist = set(parse_csv_list(args.allow_isotopes))
        missing = sorted(whitelist - set(all_isotopes))
        if missing:
            raise ValueError(f"Unknown isotopes in --allow-isotopes: {', '.join(missing)}")
        allowed &= whitelist

    if args.exclude_isotopes:
        blacklist = set(parse_csv_list(args.exclude_isotopes))
        missing = sorted(blacklist - set(all_isotopes))
        if missing:
            raise ValueError(f"Unknown isotopes in --exclude-isotopes: {', '.join(missing)}")
        allowed -= blacklist

    candidates = sorted(allowed)
    if not candidates:
        raise ValueError("No isotopes available after allow/exclude filtering.")

    max_iso = min(args.max_isotopes, len(candidates))
    min_iso = min(args.min_isotopes, max_iso)
    n_isotopes = rng.randint(min_iso, max_iso)
    chosen_isotopes = rng.sample(candidates, n_isotopes)

    use_log = args.activity_distribution == "log"
    selected: List[Tuple[str, float]] = [
        (iso, random_activity(rng, args.activity_min, args.activity_max, use_log))
        for iso in chosen_isotopes
    ]

    include_bg = choose_background(args.background_mode, rng)

    alias = {
        "poly": "Polyethylene",
        "al": "Aluminum",
        "ss": "Stainless Steel 316",
        "w": "Tungsten",
        "du": "Depleted Uranium (DU)",
        "pb": "Pb",
    }
    allowed_shields = list(SHIELDING_MATERIALS)
    if args.shield_materials:
        raw = parse_csv_list(args.shield_materials)
        mapped = []
        for item in raw:
            key = item.strip().lower()
            mapped_name = alias.get(key, item)
            if mapped_name not in SHIELDING_MATERIALS:
                raise ValueError(f"Unknown shield material: {item}")
            mapped.append(mapped_name)
        # unique preserve order
        seen = set()
        allowed_shields = [x for x in mapped if not (x in seen or seen.add(x))]

    shielding_cm: Dict[str, float] = {m: 0.0 for m in SHIELDING_MATERIALS}
    if model.has_shielding and choose_shield_enabled(args.shield_mode, rng) and args.max_shield_materials > 0:
        max_active = min(args.max_shield_materials, len(allowed_shields))
        n_active = rng.randint(1, max_active)
        active_materials = rng.sample(allowed_shields, n_active)
        for m in active_materials:
            shielding_cm[m] = rng.uniform(args.shield_min_cm, args.shield_max_cm)

    inp = CalcInputs(
        isotopes=selected,
        count_time_sec=args.count_time,
        distance_cm=args.distance_cm,
        include_background=include_bg,
        shielding_cm=shielding_cm,
    )
    res = model.compute(inp)

    if args.output:
        requested_path = Path(args.output).expanduser().resolve()
        output_format = args.format
        out_path = ensure_format_extension(requested_path, output_format)
    else:
        output_format = args.format
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = build_default_filename(
            selected,
            include_bg,
            shielding_cm,
            ts,
            extension=extension_for_format(output_format),
        )
        out_path = Path.cwd() / out_name

    out_path.parent.mkdir(parents=True, exist_ok=True)
    written_format = write_spectrum_file(out_path, inp, res, output_format)

    print(f"Wrote {written_format.upper()}: {out_path}")
    print(f"Data catalog: {model.data_path}")
    print(f"Background: {'YES' if include_bg else 'NO'}")
    print("Selected isotopes:")
    for name, act in selected:
        print(f"  - {name}: {act:.6E} Ci")
    if any(v > 0 for v in shielding_cm.values()):
        print("Shielding (cm):")
        for m in SHIELDING_MATERIALS:
            if shielding_cm[m] > 0:
                print(f"  - {m}: {shielding_cm[m]:.4f}")
    else:
        print("Shielding: none")


if __name__ == "__main__":
    main()
