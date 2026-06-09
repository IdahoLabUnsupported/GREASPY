# Changelog

All notable changes to GREASPY will be documented in this file.

## [Unreleased]

- Add shared spectrum exporters for `.spe`, `.chn`, `.n42`, and ORTEC real-format `.spc` files.
- Rename command-line spectrum scripts from `*_spe.py` to `*_spectrum.py`.
- Add CI validation for all supported spectrum export formats.
- Fix GUI shutdown so closing the GREASPY window also exits the packaged executable process.

## [1.0.0] - 2026-06-09

- Add README-style About dialog content and README authors/version sections.
- Add a deterministic `.spe` generator with direct CLI inputs and JSON parameter-file sweeps.
- Print a Eu-152 fixture comparison summary in CI logs.
- Make the INL430125 batch CLI help path independent of Tkinter for headless CI runners.
- Make GitLab CI validation shell-runner friendly by removing pip installation from the validate path.
- Add a deterministic Eu-152 `.spe` fixture comparison to CI validation.
- Add GitLab CI validation and release artifact packaging.
- Allow GREASPY calculation modules to import in headless CI environments.
- Add project license and changelog.

## [0.2.0] - 2026-06-09

### Added

- Packaged validated GREASPY data catalog for runtime calculations.
- Tracked rebuilt Windows executable at `bin/GREASPY.exe`.
- Build requirements file and README instructions for rebuilding the executable.

### Changed

- Removed the runtime dependency on the original Excel workbook.
- Removed `--workbook` from command-line tools.
- Removed `openpyxl` from runtime requirements.

## [0.1.0] - 2026-06-09

### Added

- Initial clean Python tools import.
- Tkinter GREASPY desktop application.
- Random single-file and batch `.spe` generation tools.
- Project README, runtime requirements, and ignore rules.
