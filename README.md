# ADMX2001 EIT Measurement System

Python-based measurement and analysis framework for an ADMX2001 impedance analyzer with an ESP32-controlled electrode multiplexer.

## Features

- ADMX2001 serial communication through an ESP32 bridge
- 16-electrode dual-ring measurement setup
- Adjacent and opposite measurement patterns
- Frequency sweeps and single-frequency measurements
- Automatic calibration and calibration profiles
- JSON measurement logging with timestamps and environmental data
- Automated long-term measurement cycles
- Impedance/sweep visualization
- Qualitative time-difference EIT reconstruction

## Repository structure

```text
config/                 Measurement and calibration configuration
src/admx_eit/           CLI, acquisition, calibration, experiments, protocol and logging
analysis/               Offline visualization and EIT analysis
data/                   Local measurement data (ignored by Git)
calibration_profiles/   Locally generated calibration profiles
legacy/                 Older scripts kept for reference
docs/                   Project documentation
```

## Installation

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## Running the terminal

From the repository root:

```bash
PYTHONPATH=src python -m admx_eit.terminal --port COM9
```

The terminal supports direct ADMX2001 commands as well as higher-level commands such as `adj`, `adj2`, `opp`, `save`, `savefreq`, `auto`, `autocalib`, `savecal <name>` and `loadcal <name>`.

## Analysis

Core responsibilities are split across `terminal.py` (CLI), `acquisition.py` (measurements), `calibration.py` (calibration workflows), and `experiment.py` (long-running automated cycles).

The `analysis/` directory contains scripts for measurement visualization, adjacent-pattern analysis, sweep comparison and qualitative difference-EIT reconstruction.

## EIT limitation

The current reconstruction is a qualitative 2D time-difference EIT approach based on a simplified circular resistive forward model. Reconstructed values should be interpreted as relative spatial-change proxies, not as absolutely calibrated conductivity values. The two electrode rings are currently reconstructed independently rather than with a joint 3D forward model.

## Data

Raw measurement data, generated CSV files, NumPy matrices and analysis outputs are intentionally excluded from Git by default. Configuration files that define the measurement/calibration procedure are version controlled.

## Status

Research prototype. Interfaces, file formats and measurement procedures may still change.
