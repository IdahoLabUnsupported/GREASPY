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


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


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


def validate_tracked_executable() -> None:
    exe = REPO_ROOT / "bin" / "GREASPY.exe"
    assert exe.exists(), "bin/GREASPY.exe is missing"
    assert exe.stat().st_size > 10_000_000, "bin/GREASPY.exe is unexpectedly small"


def main() -> None:
    validate_data_catalog()
    validate_reference_calculation()
    validate_cli_tools()
    validate_tracked_executable()
    print("GREASPY CI validation passed.")


if __name__ == "__main__":
    main()

