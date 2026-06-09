# GREASPY

Python tools for running GREASE/GREASY spectrum calculations and generating
PeakEasy-compatible `.spe` files.

This repository intentionally contains only the Python tooling. Original Excel
workbooks, validation artifacts, generated spectra, packaged executables, and
build outputs are not tracked here.

## Repository Contents

- `tools/GREASPY.py` - Tkinter desktop application and shared calculation engine.
- `tools/GREASPY_random_spe.py` - command-line generator for one randomized `.spe` file.
- `tools/GREASPY_batch_random_spe.py` - command-line generator for batches of randomized `.spe` files.
- `tools/GREASPY_batch_random_spe-INL430125.py` - INL430125 batch-generation variant with manifest output and optional folder picker.
- `requirements.txt` - Python package dependencies.

## Requirements

- Python 3.10 or newer
- A compatible GREASE/GREASY workbook supplied separately
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

## Workbook Input

The Python tools read workbook data at runtime, but workbook files are not stored
in this repository. Use `--workbook` for command-line tools, or place a compatible
workbook such as `GREASY_Rev3.xlsx` beside the script or in the working directory.

## Usage

Run the GUI:

```powershell
python .\tools\GREASPY.py
```

Generate one randomized `.spe` file:

```powershell
python .\tools\GREASPY_random_spe.py --workbook C:\path\to\GREASY_Rev3.xlsx --output output\sample.spe
```

Generate a batch of randomized `.spe` files:

```powershell
python .\tools\GREASPY_batch_random_spe.py --workbook C:\path\to\GREASY_Rev3.xlsx --outdir output\batch --count 100
```

Run the INL430125 batch variant:

```powershell
python .\tools\GREASPY_batch_random_spe-INL430125.py --workbook C:\path\to\GREASY_Rev3.xlsx --outdir output\batch --samples 100
```

Use `--help` with any command-line script to see its full option set.

## What Stays Out

The repo excludes:

- Excel workbook source files (`*.xlsx`, `*.xlsm`, `*.xls`)
- validation harnesses, validation cases, and validation artifacts
- generated `.spe` and `.csv` outputs
- PyInstaller `build/` and `dist/` folders
- Python caches and virtual environments

