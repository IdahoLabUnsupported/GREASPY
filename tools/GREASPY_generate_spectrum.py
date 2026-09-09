#!/usr/bin/env python3
# Copyright 2026, Battelle Energy Alliance, LLC. All Rights Reserved.
"""
Generate deterministic spectrum files using GREASPY inputs.

Examples:
  python GREASPY_generate_spectrum.py --isotope Eu152=1e-6 --count-time 600 --distance-cm 10 --background on --output eu152.spe
  python GREASPY_generate_spectrum.py --format chn --isotope Eu152=1e-6 --count-time 600 --distance-cm 10 --output eu152.chn
  python GREASPY_generate_spectrum.py --parameters parameters.json --outdir output
  python GREASPY_generate_spectrum.py --write-example parameters.example.json
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import itertools
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from GREASPY import CalcInputs, GreaseDataModel, SHIELDING_MATERIALS
from GREASPY_export import (
    SUPPORTED_SPECTRUM_FORMATS,
    ensure_format_extension,
    write_spectrum_file,
)


DEFAULT_CASE_NAME = "greaspy_spectrum"
MAX_ISOTOPES = 10

KEY_ALIASES = {
    "background": "include_background",
    "include_bg": "include_background",
    "count_time": "count_time_sec",
    "live_time": "count_time_sec",
    "live_time_sec": "count_time_sec",
    "distance": "distance_cm",
    "shielding": "shielding_cm",
}

SHIELD_ALIASES = {
    "poly": "Polyethylene",
    "polyethylene": "Polyethylene",
    "al": "Aluminum",
    "aluminum": "Aluminum",
    "ss": "Stainless Steel 316",
    "stainless": "Stainless Steel 316",
    "stainless steel": "Stainless Steel 316",
    "stainless steel 316": "Stainless Steel 316",
    "w": "Tungsten",
    "tungsten": "Tungsten",
    "pb": "Pb",
    "lead": "Pb",
    "du": "Depleted Uranium (DU)",
    "depleted uranium": "Depleted Uranium (DU)",
    "depleted uranium (du)": "Depleted Uranium (DU)",
}


def _safe_token(value: str) -> str:
    out = []
    for ch in value:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", ".", "(", ")", "/", "_"):
            out.append("_")
    token = "".join(out)
    while "__" in token:
        token = token.replace("__", "_")
    return token.strip("_") or DEFAULT_CASE_NAME


def canonical_key(key: str) -> str:
    return KEY_ALIASES.get(key, key)


def canonical_shield_material(raw: str) -> str:
    key = raw.strip().lower()
    material = SHIELD_ALIASES.get(key, raw.strip())
    if material not in SHIELDING_MATERIALS:
        valid = ", ".join(SHIELDING_MATERIALS)
        raise ValueError(f"Unknown shield material '{raw}'. Valid materials: {valid}")
    return material


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    if raw in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ValueError(f"Expected a boolean value, got {value!r}")


def parse_assignment(raw: str, label: str) -> Tuple[str, float]:
    if "=" in raw:
        name, value = raw.split("=", 1)
    elif ":" in raw:
        name, value = raw.split(":", 1)
    else:
        raise ValueError(f"{label} must use NAME=VALUE syntax; got {raw!r}")
    name = name.strip()
    if not name:
        raise ValueError(f"{label} name cannot be blank")
    return name, float(value)


def parse_cli_isotopes(values: Sequence[str]) -> List[Dict[str, Any]]:
    return [
        {"name": name, "activity_ci": activity}
        for name, activity in (parse_assignment(raw, "--isotope") for raw in values)
    ]


def parse_cli_shielding(values: Sequence[str]) -> Dict[str, float]:
    shielding: Dict[str, float] = {}
    for raw in values:
        name, thickness = parse_assignment(raw, "--shield")
        shielding[canonical_shield_material(name)] = thickness
    return shielding


def normalize_isotopes(raw: Any, model: GreaseDataModel) -> List[Tuple[str, float]]:
    if raw is None:
        raise ValueError("At least one isotope is required.")

    entries: Iterable[Any]
    if isinstance(raw, dict):
        entries = [{"name": name, "activity_ci": activity} for name, activity in raw.items()]
    elif isinstance(raw, list):
        entries = raw
    else:
        raise ValueError("'isotopes' must be a list or object mapping isotope names to activities.")

    known = set(model.isotope_names())
    isotopes: List[Tuple[str, float]] = []
    for idx, item in enumerate(entries, start=1):
        if isinstance(item, str):
            name, activity = parse_assignment(item, f"isotope entry {idx}")
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            activity_raw = item.get("activity_ci", item.get("activity", item.get("ci")))
            if activity_raw is None:
                raise ValueError(f"Isotope entry {idx} is missing activity_ci.")
            activity = float(activity_raw)
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            name = str(item[0]).strip()
            activity = float(item[1])
        else:
            raise ValueError(f"Unsupported isotope entry {idx}: {item!r}")

        if name not in known:
            raise ValueError(f"Unknown isotope '{name}'.")
        if activity <= 0:
            raise ValueError(f"Activity for isotope '{name}' must be > 0 Ci.")
        isotopes.append((name, activity))

    if not isotopes:
        raise ValueError("At least one isotope is required.")
    if len(isotopes) > MAX_ISOTOPES:
        raise ValueError(f"GREASPY supports at most {MAX_ISOTOPES} isotopes per spectrum.")
    return isotopes


def normalize_shielding(raw: Any) -> Dict[str, float]:
    shielding = {m: 0.0 for m in SHIELDING_MATERIALS}
    if raw in (None, ""):
        return shielding
    if not isinstance(raw, dict):
        raise ValueError("'shielding_cm' must be an object mapping material names to thicknesses.")

    for name, value in raw.items():
        material = canonical_shield_material(str(name))
        thickness = float(value)
        if thickness < 0:
            raise ValueError(f"Shield thickness for {material} must be >= 0 cm.")
        shielding[material] = thickness
    return shielding


def merge_case(defaults: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(defaults)
    for key, value in overrides.items():
        ckey = canonical_key(key)
        if ckey == "shielding_cm" and isinstance(value, dict):
            base = copy.deepcopy(merged.get("shielding_cm", {}))
            base.update(value)
            merged["shielding_cm"] = base
        else:
            merged[ckey] = copy.deepcopy(value)
    return merged


def numeric_range(start: float, stop: float, step: float) -> List[float]:
    if step == 0:
        raise ValueError("Range step cannot be zero.")
    if (stop - start) * step < 0:
        raise ValueError("Range step must move from start toward stop.")

    values: List[float] = []
    i = 0
    epsilon = abs(step) * 1e-9
    while True:
        current = start + step * i
        if step > 0 and current > stop + epsilon:
            break
        if step < 0 and current < stop - epsilon:
            break
        values.append(current)
        i += 1
    return values


def values_from_spec(spec: Any) -> List[Any]:
    if isinstance(spec, dict):
        if "values" in spec:
            values = spec["values"]
            return values if isinstance(values, list) else [values]
        if {"start", "stop", "step"} <= set(spec):
            return numeric_range(float(spec["start"]), float(spec["stop"]), float(spec["step"]))
        if {"start", "stop", "count"} <= set(spec):
            count = int(spec["count"])
            if count < 1:
                raise ValueError("Range count must be >= 1.")
            start = float(spec["start"])
            stop = float(spec["stop"])
            if count == 1:
                return [start]
            return [start + (stop - start) * i / (count - 1) for i in range(count)]
    if isinstance(spec, list):
        return spec
    return [spec]


def set_case_path(case: Dict[str, Any], path: str, value: Any) -> None:
    path = canonical_key(path)
    if path == "activity_ci":
        isotopes = case.get("isotopes")
        if not isinstance(isotopes, list) or len(isotopes) != 1 or not isinstance(isotopes[0], dict):
            raise ValueError("Sweep path 'activity_ci' requires exactly one isotope in the base case.")
        isotopes[0]["activity_ci"] = value
        return

    if path.startswith("shielding_cm."):
        material = canonical_shield_material(path.split(".", 1)[1])
        case.setdefault("shielding_cm", {})[material] = value
        return

    if path.startswith("isotopes."):
        parts = path.split(".")
        if len(parts) != 3 or parts[2] not in {"name", "activity_ci", "activity"}:
            raise ValueError("Isotope sweep paths must look like isotopes.0.activity_ci or isotopes.0.name.")
        idx = int(parts[1])
        isotopes = case.get("isotopes")
        if not isinstance(isotopes, list) or idx < 0 or idx >= len(isotopes):
            raise ValueError(f"Sweep path {path!r} refers to an isotope slot that does not exist.")
        if not isinstance(isotopes[idx], dict):
            raise ValueError(f"Sweep path {path!r} requires isotope entries to be objects.")
        target_key = "activity_ci" if parts[2] == "activity" else parts[2]
        isotopes[idx][target_key] = value
        return

    case[path] = value


def expand_sweep(defaults: Dict[str, Any], sweep: Dict[str, Any]) -> List[Dict[str, Any]]:
    base = merge_case(defaults, sweep.get("base", {}))
    parameters = sweep.get("parameters", sweep.get("vary"))
    if not isinstance(parameters, dict) or not parameters:
        raise ValueError("Each sweep requires a non-empty 'parameters' object.")

    mode = str(sweep.get("mode", "grid")).lower()
    paths = list(parameters)
    value_lists = [values_from_spec(parameters[path]) for path in paths]
    if any(len(values) == 0 for values in value_lists):
        raise ValueError("Sweep parameter value lists cannot be empty.")

    if mode == "grid":
        combos = list(itertools.product(*value_lists))
    elif mode == "zip":
        lengths = {len(values) for values in value_lists}
        if len(lengths) != 1:
            raise ValueError("Zip sweeps require every parameter to have the same number of values.")
        combos = list(zip(*value_lists))
    else:
        raise ValueError("Sweep mode must be 'grid' or 'zip'.")

    prefix = _safe_token(str(sweep.get("name", sweep.get("output_prefix", DEFAULT_CASE_NAME))))
    output_prefix = _safe_token(str(sweep.get("output_prefix", prefix)))
    cases: List[Dict[str, Any]] = []
    for index, combo in enumerate(combos, start=1):
        case = copy.deepcopy(base)
        for path, value in zip(paths, combo):
            set_case_path(case, path, value)
        case.setdefault("name", f"{prefix}_{index:04d}")
        case.setdefault("output", f"{output_prefix}_{index:04d}")
        cases.append(case)
    return cases


def load_parameter_cases(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Parameter file root must be a JSON object.")

    defaults = payload.get("defaults", {})
    if defaults and not isinstance(defaults, dict):
        raise ValueError("'defaults' must be an object.")

    cases: List[Dict[str, Any]] = []
    explicit_cases = payload.get("cases")
    if explicit_cases is not None:
        if not isinstance(explicit_cases, list):
            raise ValueError("'cases' must be a list.")
        for case in explicit_cases:
            if not isinstance(case, dict):
                raise ValueError("Each item in 'cases' must be an object.")
            cases.append(merge_case(defaults, case))

    sweeps = payload.get("sweeps", payload.get("sweep"))
    if sweeps is not None:
        sweep_items = sweeps if isinstance(sweeps, list) else [sweeps]
        for sweep in sweep_items:
            if not isinstance(sweep, dict):
                raise ValueError("Each sweep must be an object.")
            cases.extend(expand_sweep(defaults, sweep))

    if not cases:
        top_level_case = {k: v for k, v in payload.items() if k != "defaults"}
        cases.append(merge_case(defaults, top_level_case))
    return cases


def normalize_case(raw: Dict[str, Any], model: GreaseDataModel) -> Dict[str, Any]:
    normalized = {canonical_key(k): copy.deepcopy(v) for k, v in raw.items()}
    isotopes = normalize_isotopes(normalized.get("isotopes"), model)
    shielding = normalize_shielding(normalized.get("shielding_cm"))

    count_time = float(normalized.get("count_time_sec", 600.0))
    distance = float(normalized.get("distance_cm", 10.0))
    include_background = parse_bool(normalized.get("include_background", True))
    if count_time <= 0:
        raise ValueError("count_time_sec must be > 0.")
    if distance <= 0:
        raise ValueError("distance_cm must be > 0.")

    name = str(normalized.get("name", DEFAULT_CASE_NAME)).strip() or DEFAULT_CASE_NAME
    return {
        "name": name,
        "output": normalized.get("output"),
        "inputs": CalcInputs(
            isotopes=isotopes,
            count_time_sec=count_time,
            distance_cm=distance,
            include_background=include_background,
            shielding_cm=shielding,
        ),
    }


def resolve_output_path(
    raw_output: Optional[Any],
    outdir: Path,
    case_name: str,
    index: int,
    total: int,
    output_format: str,
) -> Path:
    if raw_output:
        path = Path(str(raw_output)).expanduser()
        if not path.is_absolute():
            path = outdir / path
        return ensure_format_extension(path.resolve(), output_format)

    stem = _safe_token(case_name)
    filename = f"{index:04d}_{stem}" if total > 1 else stem
    filename = f"{filename}.{output_format}"
    return (outdir / filename).resolve()


def manifest_entry(index: int, case_name: str, out_path: Path, inp: CalcInputs) -> Dict[str, Any]:
    return {
        "index": index,
        "name": case_name,
        "output": str(out_path),
        "count_time_sec": inp.count_time_sec,
        "distance_cm": inp.distance_cm,
        "include_background": inp.include_background,
        "isotopes": [
            {"name": name, "activity_ci": activity}
            for name, activity in inp.isotopes
        ],
        "shielding_cm": {
            material: thickness
            for material, thickness in inp.shielding_cm.items()
            if thickness > 0
        },
    }


def write_example(path: Path) -> None:
    example = {
        "defaults": {
            "isotopes": [{"name": "Eu152", "activity_ci": 1e-6}],
            "count_time_sec": 600,
            "distance_cm": 10,
            "include_background": True,
            "shielding_cm": {"Pb": 0.0},
        },
        "cases": [
            {
                "name": "eu152_single_10cm",
                "output": "eu152_single_10cm.spe",
            }
        ],
        "sweeps": [
            {
                "name": "eu152_distance_sweep",
                "output_prefix": "eu152_distance",
                "parameters": {
                    "distance_cm": {"start": 10, "stop": 30, "step": 10},
                    "include_background": [True, False],
                },
            },
            {
                "name": "eu152_activity_zip",
                "mode": "zip",
                "parameters": {
                    "activity_ci": {"values": [1e-6, 5e-6, 1e-5]},
                    "shielding_cm.Pb": {"values": [0.0, 0.25, 0.5]},
                },
            },
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(example, indent=2) + "\n", encoding="utf-8")


def build_cli_case(args: argparse.Namespace) -> Dict[str, Any]:
    if not args.isotope:
        raise ValueError("Provide at least one --isotope NAME=ACTIVITY_CI, or use --parameters.")
    case: Dict[str, Any] = {
        "name": args.name or DEFAULT_CASE_NAME,
        "isotopes": parse_cli_isotopes(args.isotope),
        "count_time_sec": args.count_time,
        "distance_cm": args.distance_cm,
        "include_background": args.background == "on",
        "shielding_cm": parse_cli_shielding(args.shield or []),
    }
    if args.output:
        case["output"] = args.output
    return case


def print_isotopes(model: GreaseDataModel) -> None:
    for name in model.isotope_names():
        print(name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic GREASPY spectrum files from CLI inputs or a JSON parameter file."
    )
    parser.add_argument("--parameters", "--parameter-file", type=str, default=None, help="JSON parameter file.")
    parser.add_argument("--outdir", type=str, default=None, help="Output directory for generated files.")
    parser.add_argument("--output", type=str, default=None, help="Output spectrum path for direct CLI mode.")
    parser.add_argument(
        "--format",
        choices=SUPPORTED_SPECTRUM_FORMATS,
        default="spe",
        help="Output format. Defaults to spe.",
    )
    parser.add_argument("--manifest", type=str, default=None, help="Optional manifest JSON path.")
    parser.add_argument("--no-manifest", action="store_true", help="Do not write a manifest JSON file.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned spectra without writing files.")
    parser.add_argument("--write-example", type=str, default=None, help="Write an example JSON parameter file and exit.")
    parser.add_argument("--list-isotopes", action="store_true", help="List isotope names in the validated data catalog.")

    parser.add_argument("--name", type=str, default=None, help="Case name for direct CLI mode.")
    parser.add_argument(
        "--isotope",
        action="append",
        default=[],
        help="Isotope/activity pair, repeatable. Example: --isotope Eu152=1e-6",
    )
    parser.add_argument("--count-time", type=float, default=600.0, help="Live counting time in seconds.")
    parser.add_argument("--distance-cm", type=float, default=10.0, help="Counting distance in cm.")
    parser.add_argument("--background", choices=["on", "off"], default="on", help="Include background counts.")
    parser.add_argument(
        "--shield",
        action="append",
        default=[],
        help="Shield material/thickness pair, repeatable. Example: --shield Pb=0.5",
    )

    args = parser.parse_args()

    if args.write_example:
        example_path = Path(args.write_example).expanduser().resolve()
        write_example(example_path)
        print(f"Wrote example parameter file: {example_path}")
        return

    model = GreaseDataModel()
    if args.list_isotopes:
        print_isotopes(model)
        return

    parameter_path = Path(args.parameters).expanduser().resolve() if args.parameters else None
    if args.outdir:
        outdir = Path(args.outdir).expanduser().resolve()
    elif parameter_path:
        outdir = parameter_path.parent
    else:
        outdir = Path.cwd().resolve()

    raw_cases = load_parameter_cases(parameter_path) if parameter_path else [build_cli_case(args)]
    cases = [normalize_case(raw, model) for raw in raw_cases]

    resolved_paths: List[Path] = []
    resolved_formats: List[str] = []
    for index, case in enumerate(cases, start=1):
        output_format = args.format
        resolved_formats.append(output_format)
        resolved_paths.append(
            resolve_output_path(case["output"], outdir, case["name"], index, len(cases), output_format)
        )

    duplicates = sorted({p for p in resolved_paths if resolved_paths.count(p) > 1})
    if duplicates:
        joined = "\n".join(f"- {path}" for path in duplicates)
        raise ValueError(f"Multiple spectra resolve to the same output path:\n{joined}")

    manifest_rows: List[Dict[str, Any]] = []
    for index, (case, out_path, output_format) in enumerate(zip(cases, resolved_paths, resolved_formats), start=1):
        inp = case["inputs"]
        row = manifest_entry(index, case["name"], out_path, inp)
        row["format"] = output_format
        manifest_rows.append(row)
        if args.dry_run:
            print(f"[dry-run] {index}/{len(cases)} {case['name']} -> {out_path}")
            continue

        res = model.compute(inp)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_spectrum_file(out_path, inp, res, output_format)
        print(f"[{index}/{len(cases)}] wrote {out_path}")

    if args.no_manifest or args.dry_run:
        return

    manifest_path: Optional[Path] = None
    if args.manifest:
        manifest_path = Path(args.manifest).expanduser()
        if not manifest_path.is_absolute():
            manifest_path = outdir / manifest_path
        manifest_path = manifest_path.resolve()
    elif parameter_path or len(cases) > 1:
        manifest_path = (outdir / "manifest.json").resolve()

    if manifest_path:
        manifest = {
            "generated_at": dt.datetime.now().isoformat(),
            "parameter_file": str(parameter_path) if parameter_path else None,
            "data_catalog": str(model.data_path),
            "data_version": model.data_version,
            "spectra_written": len(cases),
            "spectra": manifest_rows,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
