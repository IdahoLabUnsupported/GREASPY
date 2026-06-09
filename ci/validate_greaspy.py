from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
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


def validate_cli_tools() -> None:
    scripts = [
        "GREASPY_random_spe.py",
        "GREASPY_batch_random_spe.py",
        "GREASPY_batch_random_spe-INL430125.py",
    ]
    for script in scripts:
        output = run([sys.executable, str(TOOLS_DIR / script), "--help"]).stdout
        assert "--workbook" not in output

    ARTIFACT_DIR.mkdir(exist_ok=True)
    smoke_spe = ARTIFACT_DIR / "greaspy_smoke.spe"
    run(
        [
            sys.executable,
            str(TOOLS_DIR / "GREASPY_random_spe.py"),
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
    run(
        [
            sys.executable,
            str(TOOLS_DIR / "GREASPY_random_spe.py"),
            "--allow-isotopes",
            "Eu152",
            "--min-isotopes",
            "1",
            "--max-isotopes",
            "1",
            "--activity-min",
            "1e-6",
            "--activity-max",
            "1e-6",
            "--count-time",
            "600",
            "--distance-cm",
            "10",
            "--background-mode",
            "on",
            "--shield-mode",
            "off",
            "--output",
            str(actual_spe),
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
    validate_cli_tools()
    record("CLI validation and smoke spectrum generation passed")
    validate_eu152_spectrum_fixture()
    record("Eu152 spectrum fixture comparison passed")
    validate_tracked_executable()
    record("tracked executable validation passed")
    print("GREASPY CI validation passed.")


if __name__ == "__main__":
    main()
