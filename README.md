<!-- Copyright 2026, Battelle Energy Alliance, LLC. All Rights Reserved. -->

# GREASPY

Python tools and a Windows executable for GREASE/GREASPY spectrum calculations
and spectrum generation in `.spe`, `.chn`, `.n42`, and `.spc` formats.

GREASPY now uses a packaged, validated data catalog at runtime. It does not
require the original Excel workbook to run.

## Version Information

- GREASPY application version: 1.0
- GREASPY release version: 1.0.0
- Validated data catalog version: 2026.03.19
- Validated data schema version: 1

## Authors

- Dr. Michael Reichenber, Idaho National Laboratory
- Dr. Tommy Holschuh, Idaho National Laboratory

## Repository Contents

- `bin/GREASPY.exe` - rebuilt Windows executable.
- `tools/GREASPY.py` - Tkinter desktop application and shared calculation engine.
- `tools/GREASPY_generate_spectrum.py` - deterministic command-line spectrum generator from direct inputs or a JSON parameter file.
- `tools/GREASPY_random_spectrum.py` - command-line generator for one randomized spectrum file.
- `tools/GREASPY_batch_random_spectrum.py` - command-line generator for batches of randomized spectrum files.
- `tools/GREASPY_batch_random_spectrum-INL430125.py` - INL430125 batch-generation variant with manifest output and optional folder picker.
- `tools/GREASPY_export.py` - shared `.spe`, `.chn`, `.n42`, and `.spc` exporters.
- `tools/data/greaspy_validated_data.json.gz` - packaged validated GREASPY data catalog.
- `CHANGELOG.md` - release history and notable project changes.
- `LICENSE` - general-use project license.
- `requirements.txt` - Python package dependencies for source runs.
- `requirements-build.txt` - extra dependency for rebuilding the executable.

## Requirements

- Python 3.10 or newer for source runs
- Windows for the tracked executable
- Python packages listed in `requirements.txt`

`tkinter` is used by the GUI tools and is normally included with the standard
Windows Python installer.

## Setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Usage

Run the tracked executable:

```powershell
.\bin\GREASPY.exe
```

Run the GUI from source:

```powershell
python .\tools\GREASPY.py
```

Generate one randomized `.spe` file:

```powershell
python .\tools\GREASPY_random_spectrum.py --output output\sample.spe
```

Generate one deterministic `.spe` file:

```powershell
python .\tools\GREASPY_generate_spectrum.py --isotope Eu152=1e-6 --count-time 600 --distance-cm 10 --background on --output output\eu152_10cm.spe
```

Generate another supported format:

```powershell
python .\tools\GREASPY_generate_spectrum.py --format n42 --isotope Eu152=1e-6 --count-time 600 --distance-cm 10 --output output\eu152_10cm.n42
```

Generate deterministic spectra from a JSON parameter file:

```powershell
python .\tools\GREASPY_generate_spectrum.py --parameters parameters.json --outdir output\parameters
```

Write a starter parameter file:

```powershell
python .\tools\GREASPY_generate_spectrum.py --write-example parameters.example.json
```

Generate a batch of randomized spectrum files:

```powershell
python .\tools\GREASPY_batch_random_spectrum.py --outdir output\batch --count 100
```

Run the INL430125 batch variant:

```powershell
python .\tools\GREASPY_batch_random_spectrum-INL430125.py --outdir output\batch --samples 100
```

Use `--help` with any command-line script to see its full option set.

### Deterministic Parameter Files

`GREASPY_generate_spectrum.py` accepts a single spectrum, explicit cases, or sweeps.
Relative output paths are written under `--outdir`; if `--outdir` is omitted,
they are written next to the parameter file.

```json
{
  "defaults": {
    "isotopes": [
      { "name": "Eu152", "activity_ci": 1e-6 }
    ],
    "count_time_sec": 600,
    "distance_cm": 10,
    "include_background": true,
    "shielding_cm": { "Pb": 0.0 }
  },
  "cases": [
    {
      "name": "eu152_single_10cm",
      "output": "eu152_single_10cm.spe"
    }
  ],
  "sweeps": [
    {
      "name": "eu152_distance_sweep",
      "output_prefix": "eu152_distance",
      "parameters": {
        "distance_cm": { "start": 10, "stop": 30, "step": 10 },
        "include_background": [true, false]
      }
    }
  ]
}
```

Sweep parameters support direct fields such as `distance_cm`,
`count_time_sec`, and `include_background`, single-isotope activity through
`activity_ci`, isotope-slot fields such as `isotopes.0.activity_ci`, and shield
thicknesses such as `shielding_cm.Pb`.

## CI/CD

GitLab CI validates every branch and merge request with source compilation,
catalog integrity checks, reference calculation checks, CLI help checks, and
export checks for `.spe`, `.chn`, `.n42`, and `.spc` spectra. It also
regenerates a fixed Eu-152 `.spe` spectrum case and compares the result
against `ci/expected/eu152_1uci_10cm_10min_bg_on_no_shield.spe`.
The pipeline log prints a compact comparison summary with normalized hashes,
channel totals, and per-channel delta information.

The validate job intentionally avoids `pip` and third-party installation so it
can run on shell runners with the system Python.

Pipelines on `main` and tags also publish `dist/greaspy-release.zip` as a job
artifact. The release zip includes the tracked executable, source tools,
validated data catalog, README, changelog, license, and requirements files.

## Changelog

See `CHANGELOG.md` for release history and notable changes.

## Rebuild the Executable

Install the source and build dependencies:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
```

Rebuild `bin/GREASPY.exe`:

```powershell
$data = (Resolve-Path "tools\data\greaspy_validated_data.json.gz").Path
pyinstaller --noconfirm --clean --onefile --windowed --name GREASPY --distpath bin --workpath build --specpath build --add-data "$data;data" tools/GREASPY.py
```

## What Stays Out

The repo excludes:

- legacy Excel workbook source files (`*.xlsx`, `*.xlsm`, `*.xls`)
- validation harnesses, validation cases, and validation artifacts
- generated `.spe`, `.chn`, `.n42`, `.spc`, and `.csv` outputs
- transient PyInstaller `build/` output
- Python caches and virtual environments

## License

GREASPY is available under the MIT License. See `LICENSE` for details.
