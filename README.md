# GREASPY

Python tools and a Windows executable for GREASE/GREASPY spectrum calculations
and PeakEasy-compatible `.spe` generation.

GREASPY now uses a packaged, validated data catalog at runtime. It does not
require the original Excel workbook to run.

## Repository Contents

- `bin/GREASPY.exe` - rebuilt Windows executable.
- `tools/GREASPY.py` - Tkinter desktop application and shared calculation engine.
- `tools/GREASPY_random_spe.py` - command-line generator for one randomized `.spe` file.
- `tools/GREASPY_batch_random_spe.py` - command-line generator for batches of randomized `.spe` files.
- `tools/GREASPY_batch_random_spe-INL430125.py` - INL430125 batch-generation variant with manifest output and optional folder picker.
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
python .\tools\GREASPY_random_spe.py --output output\sample.spe
```

Generate a batch of randomized `.spe` files:

```powershell
python .\tools\GREASPY_batch_random_spe.py --outdir output\batch --count 100
```

Run the INL430125 batch variant:

```powershell
python .\tools\GREASPY_batch_random_spe-INL430125.py --outdir output\batch --samples 100
```

Use `--help` with any command-line script to see its full option set.

## CI/CD

GitLab CI validates every branch and merge request with source compilation,
catalog integrity checks, reference calculation checks, CLI help checks, and a
smoke-generated `.spe` artifact. It also regenerates a fixed Eu-152 spectrum
case and compares the result against `ci/expected/eu152_1uci_10cm_10min_bg_on_no_shield.spe`.
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
- generated `.spe` and `.csv` outputs
- transient PyInstaller `build/` output
- Python caches and virtual environments

## License

GREASPY is available under the MIT License. See `LICENSE` for details.
