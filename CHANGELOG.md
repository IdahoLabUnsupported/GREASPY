# Changelog

All notable changes to GREASPY will be documented in this file.

## [Unreleased]

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
