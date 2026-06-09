from __future__ import annotations

import gzip
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
