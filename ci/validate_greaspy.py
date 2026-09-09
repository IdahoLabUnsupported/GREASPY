# Copyright 2026, Battelle Energy Alliance, LLC. All Rights Reserved.
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
ARTIFACT_DIR = REPO_ROOT / "ci_artifacts"
DATA_PATH = TOOLS_DIR / "data" / "greaspy_validated_data.json.gz"
EXPECTED_EU152_SPE = REPO_ROOT / "ci" / "expected" / "eu152_1uci_10cm_10min_bg_on_no_shield.spe"
SUMMARY_PATH = ARTIFACT_DIR / "validation-summary.txt"


def record(message: str) -> None:
    ARTIFACT_DIR.mkdir(exist_ok=True)
    with SUMMARY_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{message}\n")


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0:
        print(result.stdout)
        raise subprocess.CalledProcessError(result.returncode, args, output=result.stdout)
    return result


def validate_data_catalog() -> None:
    with gzip.open(DATA_PATH, "rt", encoding="utf-8") as f:
        data = json.load(f)

    assert data["schema_version"] == 1
    assert data["num_bins"] == 16384
    assert data["source"]["profile"] == "common"
    assert len(data["source"]["sha256"]) == 64
    assert len(data["energy_kev"]) == 16384
    assert len(data["background_cps"]) == 16384
    assert len(data["isotopes"]) == 147
    assert set(data["shield_mu"]) == set(data["shielding_materials"])


def validate_reference_calculation() -> None:
    sys.path.insert(0, str(TOOLS_DIR))
    from GREASPY import CalcInputs, GreaseDataModel, SHIELDING_MATERIALS

    model = GreaseDataModel()
    shielding = {m: 0.0 for m in SHIELDING_MATERIALS}
    shielding["Pb"] = 0.5
    inp = CalcInputs(
        isotopes=[("Cs137", 1e-6), ("Co60", 2e-7)],
        count_time_sec=300.0,
        distance_cm=20.0,
        include_background=True,
        shielding_cm=shielding,
    )
    res = model.compute(inp)

    expected = {
        "total_sum": 6.911094258278e04,
        "dose": 2.741103320194e-06,
        "dead_time": 2.174406890976e-01,
        "shielded_dose": 2.321527757295e-07,
    }
    actual = {
        "total_sum": sum(res.total_counts),
        "dose": res.unshielded_dose_30cm,
        "dead_time": res.unshielded_dead_time_pct,
        "shielded_dose": res.shielded_dose_30cm,
    }

    for name, expected_value in expected.items():
        value = actual[name]
        tolerance = max(1e-12, abs(expected_value) * 1e-10)
        assert abs(value - expected_value) <= tolerance, (
            f"{name}: got {value}, expected {expected_value}"
        )


def validate_export_formats() -> None:
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    from GREASPY import CalcInputs, GreaseDataModel, SHIELDING_MATERIALS
    from GREASPY_export import (
        N42_NAMESPACE,
        build_chn_bytes,
        build_n42_text,
        build_spc_bytes,
        write_spectrum_file,
    )

    model = GreaseDataModel()
    inp = CalcInputs(
        isotopes=[("Eu152", 1e-6)],
        count_time_sec=600.0,
        distance_cm=10.0,
        include_background=True,
        shielding_cm={m: 0.0 for m in SHIELDING_MATERIALS},
    )
    res = model.compute(inp)
    measured_at = dt.datetime(2026, 6, 9, 12, 34, 56)
    channel_count = len(res.total_counts)

    chn = build_chn_bytes(inp, res, measurement_datetime=measured_at)
    assert len(chn) == 32 + channel_count * 4 + 512
    assert struct.unpack_from("<h", chn, 0)[0] == -1
    assert struct.unpack_from("<h", chn, 30)[0] == channel_count
    assert chn[16:24] == b"09JUN261"
    assert struct.unpack_from("<i", chn, 32)[0] == round(res.total_counts[0])
    trailer_offset = 32 + channel_count * 4
    assert struct.unpack_from("<h", chn, trailer_offset)[0] == -102
    assert abs(struct.unpack_from("<f", chn, trailer_offset + 8)[0] - res.eff_b) < 1e-6

    spc = build_spc_bytes(inp, res, measurement_datetime=measured_at)
    assert len(spc) % 128 == 0
    assert struct.unpack_from("<h", spc, 0)[0] == 1
    assert struct.unpack_from("<h", spc, 2)[0] == 5
    first_spectrum_record = struct.unpack_from("<h", spc, 60)[0]
    spectrum_record_count = struct.unpack_from("<h", spc, 62)[0]
    assert first_spectrum_record == 7
    assert spectrum_record_count == channel_count // 32
    assert struct.unpack_from("<h", spc, 64)[0] == channel_count
    first_spc_count = struct.unpack_from("<f", spc, (first_spectrum_record - 1) * 128)[0]
    assert abs(first_spc_count - res.total_counts[0]) < max(1e-3, abs(res.total_counts[0]) * 1e-6)

    n42 = build_n42_text(
        inp,
        res,
        measurement_datetime=measured_at,
        document_uuid="00000000-0000-4000-8000-000000000000",
    )
    root = ET.fromstring(n42)
    ns = {"n": N42_NAMESPACE}
    assert root.tag == f"{{{N42_NAMESPACE}}}RadInstrumentData"
    coeffs = root.find(".//n:EnergyCalibration/n:CoefficientValues", ns)
    assert coeffs is not None
    assert coeffs.text is not None and coeffs.text.split()[:2] == [f"{res.eff_a:.6f}", f"{res.eff_b:.6f}"]
    channel_data = root.find(".//n:Spectrum/n:ChannelData", ns)
    assert channel_data is not None and channel_data.text is not None
    assert len(channel_data.text.split()) == channel_count

    ARTIFACT_DIR.mkdir(exist_ok=True)
    for format_name in ("spe", "chn", "n42", "spc"):
        out_path = ARTIFACT_DIR / f"export_smoke.{format_name}"
        write_spectrum_file(out_path, inp, res, format_name, measurement_datetime=measured_at)
        assert out_path.exists()
        assert out_path.stat().st_size > 100


def validate_cli_tools() -> None:
    scripts = [
        "GREASPY_generate_spectrum.py",
        "GREASPY_random_spectrum.py",
        "GREASPY_batch_random_spectrum.py",
        "GREASPY_batch_random_spectrum-INL430125.py",
    ]
    for script in scripts:
        output = run([sys.executable, str(TOOLS_DIR / script), "--help"]).stdout
        assert "--workbook" not in output

    ARTIFACT_DIR.mkdir(exist_ok=True)
    smoke_spe = ARTIFACT_DIR / "greaspy_smoke.spe"
    run(
        [
            sys.executable,
            str(TOOLS_DIR / "GREASPY_random_spectrum.py"),
            "--seed",
            "42",
            "--output",
            str(smoke_spe),
        ]
    )
    text = smoke_spe.read_text(encoding="utf-8")
    assert text.startswith("$SPEC_ID:\n")
    assert "$DATA:\n" in text
    assert "$ENER_FIT:\n" in text

    deterministic_spe = ARTIFACT_DIR / "greaspy_deterministic_eu152.spe"
    run(
        [
            sys.executable,
            str(TOOLS_DIR / "GREASPY_generate_spectrum.py"),
            "--isotope",
            "Eu152=1e-6",
            "--count-time",
            "600",
            "--distance-cm",
            "10",
            "--background",
            "on",
            "--output",
            str(deterministic_spe),
        ]
    )
    deterministic_text = deterministic_spe.read_text(encoding="utf-8")
    assert "Isotope 1: Eu152 = 1.00E-06 Ci" in deterministic_text
    assert "Distance Measured = 10 cm" in deterministic_text

    cli_format_dir = ARTIFACT_DIR / "cli_format_exports"
    cli_format_dir.mkdir(exist_ok=True)
    default_base = cli_format_dir / "default_format"
    run(
        [
            sys.executable,
            str(TOOLS_DIR / "GREASPY_generate_spectrum.py"),
            "--isotope",
            "Eu152=1e-6",
            "--count-time",
            "600",
            "--distance-cm",
            "10",
            "--background",
            "on",
            "--output",
            str(default_base),
        ]
    )
    assert default_base.with_suffix(".spe").exists()

    for format_name in ("spe", "chn", "n42", "spc"):
        output_base = cli_format_dir / f"eu152_{format_name}"
        run(
            [
                sys.executable,
                str(TOOLS_DIR / "GREASPY_generate_spectrum.py"),
                "--format",
                format_name,
                "--isotope",
                "Eu152=1e-6",
                "--count-time",
                "600",
                "--distance-cm",
                "10",
                "--background",
                "on",
                "--output",
                str(output_base),
            ]
        )
        output_path = output_base.with_suffix(f".{format_name}")
        assert output_path.exists()
        if format_name == "spe":
            export_text = output_path.read_text(encoding="utf-8")
            assert export_text.startswith("$SPEC_ID:\n")
        elif format_name == "chn":
            export_bytes = output_path.read_bytes()
            assert struct.unpack_from("<h", export_bytes, 0)[0] == -1
            assert struct.unpack_from("<h", export_bytes, 30)[0] == 16384
        elif format_name == "n42":
            root = ET.fromstring(output_path.read_text(encoding="utf-8"))
            assert root.tag == "{http://physics.nist.gov/N42/2011/N42}RadInstrumentData"
        elif format_name == "spc":
            export_bytes = output_path.read_bytes()
            assert struct.unpack_from("<h", export_bytes, 0)[0] == 1
            assert struct.unpack_from("<h", export_bytes, 2)[0] == 5

    parameter_file = ARTIFACT_DIR / "greaspy_parameters.json"
    parameter_outdir = ARTIFACT_DIR / "parameter_sweep"
    parameter_manifest = ARTIFACT_DIR / "parameter_sweep_manifest.json"
    parameter_file.write_text(
        json.dumps(
            {
                "defaults": {
                    "isotopes": [{"name": "Eu152", "activity_ci": 1e-6}],
                    "count_time_sec": 600,
                    "distance_cm": 10,
                    "include_background": True,
                    "shielding_cm": {"Pb": 0.0},
                },
                "sweeps": [
                    {
                        "name": "eu152_distance",
                        "parameters": {
                            "distance_cm": {"values": [10, 20]},
                        },
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    run(
        [
            sys.executable,
            str(TOOLS_DIR / "GREASPY_generate_spectrum.py"),
            "--parameters",
            str(parameter_file),
            "--outdir",
            str(parameter_outdir),
            "--manifest",
            str(parameter_manifest),
        ]
    )
    generated_parameter_spectra = sorted(parameter_outdir.glob("*.spe"))
    assert len(generated_parameter_spectra) == 2
    manifest = json.loads(parameter_manifest.read_text(encoding="utf-8"))
    assert manifest["spectra_written"] == 2
    assert [row["distance_cm"] for row in manifest["spectra"]] == [10.0, 20.0]


def normalized_spe_lines(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for i, line in enumerate(lines[:-1]):
        if line == "$DATE_MEA:":
            lines[i + 1] = "<normalized measurement date>"
            return lines
    raise AssertionError(f"{path} does not contain a $DATE_MEA section")


def normalized_spe_sha256(lines: list[str]) -> str:
    text = "\n".join(lines) + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_spe_counts(lines: list[str], path: Path) -> tuple[int, int, list[float]]:
    try:
        data_idx = lines.index("$DATA:")
        fit_idx = lines.index("$ENER_FIT:")
    except ValueError as exc:
        raise AssertionError(f"{path} does not contain expected $DATA/$ENER_FIT sections") from exc

    start_txt, end_txt = lines[data_idx + 1].split()
    start = int(start_txt)
    end = int(end_txt)
    counts = [float(v) for v in lines[data_idx + 2:fit_idx]]
    expected_count = end - start + 1
    assert len(counts) == expected_count, (
        f"{path} contains {len(counts)} count channels; expected {expected_count}"
    )
    return start, end, counts


def eu152_comparison_summary(expected: list[str], actual: list[str], actual_path: Path) -> list[str]:
    exp_start, exp_end, exp_counts = extract_spe_counts(expected, EXPECTED_EU152_SPE)
    act_start, act_end, act_counts = extract_spe_counts(actual, actual_path)
    assert (act_start, act_end) == (exp_start, exp_end), (
        f"Generated spectrum channel range {act_start}-{act_end} does not match "
        f"fixture range {exp_start}-{exp_end}"
    )
    assert len(act_counts) == len(exp_counts), "Generated and fixture spectra have different channel counts"

    deltas = [actual_count - expected_count for expected_count, actual_count in zip(exp_counts, act_counts)]
    max_abs_delta = max((abs(delta) for delta in deltas), default=0.0)
    total_expected = sum(exp_counts)
    total_actual = sum(act_counts)
    total_delta = total_actual - total_expected
    line_match = actual == expected

    summary = [
        "Eu152 fixture comparison summary:",
        f"- expected artifact: {EXPECTED_EU152_SPE.relative_to(REPO_ROOT)}",
        f"- generated artifact: {actual_path.relative_to(REPO_ROOT)}",
        f"- normalized expected SHA256: {normalized_spe_sha256(expected)}",
        f"- normalized generated SHA256: {normalized_spe_sha256(actual)}",
        f"- normalized line comparison: {'MATCH' if line_match else 'DIFFER'}",
        f"- channels compared: {len(exp_counts)} ({exp_start}-{exp_end})",
        f"- expected total counts: {total_expected:.6f}",
        f"- generated total counts: {total_actual:.6f}",
        f"- total count delta: {total_delta:.6e}",
        f"- max channel absolute delta: {max_abs_delta:.6e}",
    ]

    if not line_match:
        for idx, (expected_line, actual_line) in enumerate(zip(expected, actual), start=1):
            if expected_line != actual_line:
                summary.extend(
                    [
                        f"- first differing normalized line: {idx}",
                        f"  expected: {expected_line}",
                        f"  actual: {actual_line}",
                    ]
                )
                break
        if len(actual) != len(expected):
            summary.append(f"- normalized line count delta: {len(actual) - len(expected)}")

    return summary


def validate_eu152_spectrum_fixture() -> None:
    ARTIFACT_DIR.mkdir(exist_ok=True)
    actual_spe = ARTIFACT_DIR / "eu152_1uci_10cm_10min_bg_on_no_shield.spe"
    parameter_file = ARTIFACT_DIR / "eu152_1uci_10cm_10min_bg_on_no_shield.json"
    parameter_file.write_text(
        json.dumps(
            {
                "name": "eu152_1uci_10cm_10min_bg_on_no_shield",
                "output": actual_spe.name,
                "isotopes": [{"name": "Eu152", "activity_ci": 1e-6}],
                "count_time_sec": 600,
                "distance_cm": 10,
                "include_background": True,
                "shielding_cm": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    run(
        [
            sys.executable,
            str(TOOLS_DIR / "GREASPY_generate_spectrum.py"),
            "--parameters",
            str(parameter_file),
            "--outdir",
            str(ARTIFACT_DIR),
            "--no-manifest",
        ]
    )

    expected = normalized_spe_lines(EXPECTED_EU152_SPE)
    actual = normalized_spe_lines(actual_spe)
    for line in eu152_comparison_summary(expected, actual, actual_spe):
        print(line)
        record(line)

    assert actual == expected, (
        "Generated Eu152 spectrum differs from the expected CI fixture "
        f"({EXPECTED_EU152_SPE})."
    )


def validate_tracked_executable() -> None:
    exe = REPO_ROOT / "bin" / "GREASPY.exe"
    assert exe.exists(), "bin/GREASPY.exe is missing"
    assert exe.stat().st_size > 10_000_000, "bin/GREASPY.exe is unexpectedly small"


def main() -> None:
    validate_data_catalog()
    record("data catalog validation passed")
    validate_reference_calculation()
    record("reference calculation validation passed")
    validate_export_formats()
    record("spectrum export format validation passed")
    validate_cli_tools()
    record("CLI validation and smoke spectrum generation passed")
    validate_eu152_spectrum_fixture()
    record("Eu152 spectrum fixture comparison passed")
    validate_tracked_executable()
    record("tracked executable validation passed")
    print("GREASPY CI validation passed.")


if __name__ == "__main__":
    main()
