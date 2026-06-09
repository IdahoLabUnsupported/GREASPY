#!/usr/bin/env python3
"""
Generate batches of randomized spectrum files using the GREASPY engine.

This script samples uniformly over the requested parameter ranges and exports
one spectrum file per sample into the selected output directory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from GREASPY import CalcInputs, GreaseDataModel, SHIELDING_MATERIALS
from GREASPY_export import (
    SUPPORTED_SPECTRUM_FORMATS,
    extension_for_format,
    write_spectrum_file,
)


def parse_csv_list(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def _safe_token(s: str) -> str:
    out: List[str] = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", ".", "(", ")", "/"):
            out.append("_")
    token = "".join(out)
    while "__" in token:
        token = token.replace("__", "_")
    return token.strip("_")


def resolve_outdir(path_arg: Optional[str]) -> Path:
    if path_arg:
        return Path(path_arg).expanduser().resolve()

    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise RuntimeError("Tkinter is not available; provide --outdir when running headlessly.") from exc

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(title="Select output directory for GREASPY batch spectrum files")
    root.destroy()

    if not selected:
        raise ValueError("No output directory selected. Provide --outdir or choose a folder.")

    return Path(selected).expanduser().resolve()


def random_activity(rng: random.Random, low: float, high: float, mode: str) -> float:
    if mode == "log":
        return 10.0 ** rng.uniform(math.log10(low), math.log10(high))
    return rng.uniform(low, high)


def choose_bool(mode: str, rng: random.Random) -> bool:
    if mode == "on":
        return True
    if mode == "off":
        return False
    return bool(rng.getrandbits(1))


def canonical_shield_materials(raw: Optional[str]) -> List[str]:
    if not raw:
        return list(SHIELDING_MATERIALS)

    alias = {
        "poly": "Polyethylene",
        "al": "Aluminum",
        "ss": "Stainless Steel 316",
        "w": "Tungsten",
        "du": "Depleted Uranium (DU)",
        "pb": "Pb",
    }
    vals = parse_csv_list(raw)
    mapped: List[str] = []
    for item in vals:
        key = item.lower().strip()
        m = alias.get(key, item)
        if m not in SHIELDING_MATERIALS:
            raise ValueError(f"Unknown shield material: {item}")
        mapped.append(m)

    seen = set()
    return [x for x in mapped if not (x in seen or seen.add(x))]


def sample_isotopes(
    rng: random.Random,
    candidates: Sequence[str],
    min_count: int,
    max_count: int,
    activity_min: float,
    activity_max: float,
    activity_mode: str,
) -> List[Tuple[str, float]]:
    n = rng.randint(min_count, max_count)
    chosen = rng.sample(list(candidates), n)
    return [
        (iso, random_activity(rng, activity_min, activity_max, activity_mode))
        for iso in chosen
    ]


def sample_shielding(
    rng: random.Random,
    enabled: bool,
    allowed_materials: Sequence[str],
    min_active: int,
    max_active: int,
    min_cm: float,
    max_cm: float,
) -> Dict[str, float]:
    shielding = {m: 0.0 for m in SHIELDING_MATERIALS}
    if not enabled:
        return shielding

    active_n = rng.randint(min_active, max_active)
    active_mats = rng.sample(list(allowed_materials), active_n)
    for m in active_mats:
        shielding[m] = rng.uniform(min_cm, max_cm)
    return shielding


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Uniformly sample GREASPY parameter space and export spectrum files."
    )
    parser.add_argument("--outdir", type=str, default=None, help="Output directory for spectrum files.")
    parser.add_argument("--samples", type=int, default=10, help="Number of samples / spectrum files.")
    parser.add_argument(
        "--format",
        choices=SUPPORTED_SPECTRUM_FORMATS,
        default="spe",
        help="Output spectrum format.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    parser.add_argument("--prefix", type=str, default="greaspy_sample", help="Output filename prefix.")
    parser.add_argument(
        "--manifest-name",
        type=str,
        default="manifest.json",
        help="JSON manifest filename written in outdir.",
    )

    parser.add_argument("--count-time-min", type=float, default=3600.0, help="Min counting time (sec).")
    parser.add_argument("--count-time-max", type=float, default=3600.0, help="Max counting time (sec).")
    parser.add_argument("--distance-min-cm", type=float, default=0.01, help="Min detector distance (cm).")
    parser.add_argument("--distance-max-cm", type=float, default=10.0, help="Max detector distance (cm).")
    parser.add_argument(
        "--background-mode",
        choices=["random", "on", "off"],
        default="random",
        help="Background sampling mode.",
    )

    parser.add_argument("--min-isotopes", type=int, default=1, help="Min isotopes per sample.")
    parser.add_argument("--max-isotopes", type=int, default=10, help="Max isotopes per sample.")
    parser.add_argument(
        "--allow-isotopes",
        type=str,
        default=None,
        help="Comma-separated isotope whitelist.",
    )
    parser.add_argument(
        "--exclude-isotopes",
        type=str,
        default=None,
        help="Comma-separated isotope blacklist.",
    )
    parser.add_argument("--activity-min", type=float, default=1e-12, help="Min activity (Ci).")
    parser.add_argument("--activity-max", type=float, default=1e-3, help="Max activity (Ci).")
    parser.add_argument(
        "--activity-distribution",
        choices=["linear", "log"],
        default="log",
        help="Uniform space for activity sampling.",
    )

    parser.add_argument(
        "--shield-mode",
        choices=["random", "on", "off"],
        default="off",
        help="Shielding sampling mode.",
    )
    parser.add_argument(
        "--shield-materials",
        type=str,
        default=None,
        help="Comma-separated materials (or aliases Poly,Al,SS,W,Pb,DU).",
    )
    parser.add_argument("--shield-material-count-min", type=int, default=1, help="Min active shield materials.")
    parser.add_argument("--shield-material-count-max", type=int, default=2, help="Max active shield materials.")
    parser.add_argument("--shield-thickness-min-cm", type=float, default=0.05, help="Min active shield thickness.")
    parser.add_argument("--shield-thickness-max-cm", type=float, default=3.0, help="Max active shield thickness.")

    args = parser.parse_args()

    if args.samples < 1:
        raise ValueError("--samples must be >= 1")
    if args.count_time_min <= 0 or args.count_time_max <= 0:
        raise ValueError("Count-time bounds must be > 0")
    if args.count_time_max < args.count_time_min:
        raise ValueError("--count-time-max must be >= --count-time-min")
    if args.distance_min_cm <= 0 or args.distance_max_cm <= 0:
        raise ValueError("Distance bounds must be > 0")
    if args.distance_max_cm < args.distance_min_cm:
        raise ValueError("--distance-max-cm must be >= --distance-min-cm")
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
    if args.shield_material_count_min < 0 or args.shield_material_count_max < 0:
        raise ValueError("Shield material counts must be >= 0")
    if args.shield_material_count_max < args.shield_material_count_min:
        raise ValueError("--shield-material-count-max must be >= --shield-material-count-min")
    if args.shield_thickness_min_cm < 0 or args.shield_thickness_max_cm < 0:
        raise ValueError("Shield thickness bounds must be >= 0")
    if args.shield_thickness_max_cm < args.shield_thickness_min_cm:
        raise ValueError("--shield-thickness-max-cm must be >= --shield-thickness-min-cm")

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
        raise ValueError("No isotopes available after allow/exclude filters.")
    if len(candidates) < args.min_isotopes:
        raise ValueError("Not enough isotope candidates for --min-isotopes.")

    max_iso = min(args.max_isotopes, len(candidates))
    min_iso = min(args.min_isotopes, max_iso)

    allowed_shields = canonical_shield_materials(args.shield_materials)
    if not model.has_shielding:
        allowed_shields = []

    if args.shield_mode == "on" and not allowed_shields:
        raise ValueError("Validated GREASPY data catalog has no shielding data or no allowed shield materials.")

    if allowed_shields:
        sh_min_n = args.shield_material_count_min
        sh_max_n = min(args.shield_material_count_max, len(allowed_shields))
    else:
        sh_min_n = 0
        sh_max_n = 0

    if sh_max_n < sh_min_n:
        raise ValueError("Shield material count bounds invalid for selected materials.")

    outdir = resolve_outdir(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    manifest_path = outdir / args.manifest_name

    rows: List[Dict[str, object]] = []
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    for i in range(1, args.samples + 1):
        count_time = rng.uniform(args.count_time_min, args.count_time_max)
        distance_cm = rng.uniform(args.distance_min_cm, args.distance_max_cm)
        include_bg = choose_bool(args.background_mode, rng)
        isotopes = sample_isotopes(
            rng=rng,
            candidates=candidates,
            min_count=min_iso,
            max_count=max_iso,
            activity_min=args.activity_min,
            activity_max=args.activity_max,
            activity_mode=args.activity_distribution,
        )

        shield_enabled = choose_bool(args.shield_mode, rng) if allowed_shields else False
        shielding_cm = sample_shielding(
            rng=rng,
            enabled=shield_enabled,
            allowed_materials=allowed_shields,
            min_active=sh_min_n if shield_enabled else 0,
            max_active=sh_max_n if shield_enabled else 0,
            min_cm=args.shield_thickness_min_cm,
            max_cm=args.shield_thickness_max_cm,
        )

        inp = CalcInputs(
            isotopes=isotopes,
            count_time_sec=count_time,
            distance_cm=distance_cm,
            include_background=include_bg,
            shielding_cm=shielding_cm,
        )
        res = model.compute(inp)

        fname = f"{_safe_token(args.prefix)}_{ts}_{i:05d}{extension_for_format(args.format)}"
        out_path = outdir / fname
        write_spectrum_file(
            out_path,
            inp,
            res,
            args.format,
            detector_description="GREASPY Batch Generator IDM-200-V",
            analysis_program="Generated by GREASPY_batch_random_spectrum-INL430125.py",
        )

        rows.append(
            {
                "index": i,
                "filename": fname,
                "format": args.format,
                "count_time_sec": count_time,
                "distance_cm": distance_cm,
                "include_background": include_bg,
                "isotopes": [
                    {"name": name, "activity_ci": act}
                    for name, act in isotopes
                ],
                "shielding_cm": {
                    m: shielding_cm[m]
                    for m in SHIELDING_MATERIALS
                    if shielding_cm[m] > 0
                },
            }
        )

        if i == 1 or i % 25 == 0 or i == args.samples:
            print(f"[{i}/{args.samples}] wrote {out_path.name}")

    manifest = {
        "data_catalog": str(model.data_path),
        "data_version": model.data_version,
        "output_directory": str(outdir),
        "samples_requested": args.samples,
        "seed": args.seed,
        "generated_at": dt.datetime.now().isoformat(),
        "samples": rows,
    }
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Data catalog: {model.data_path}")
    print(f"Output directory: {outdir}")
    print(f"Samples written: {args.samples}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
