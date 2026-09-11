# EIT Host

Host-side Python software for an Electrical Impedance Tomography (EIT) measurement system based on an **ADMX2001 Precision Impedance Analyzer** and an **ESP32-controlled electrode multiplexer**.

The software provides serial communication with the measurement hardware, electrode switching, impedance measurements, frequency sweeps, automated measurement sequences, calibration handling, JSON logging, and analysis tools.

## System Overview

The current setup consists of:

- ADMX2001 Precision Impedance Analyzer
- ESP32-S3 running the EIT firmware
- ESP32-controlled electrode multiplexer
- 16 electrodes arranged as two rings
  - Ring 1: electrodes 1–8
  - Ring 2: electrodes 9–16
- Python host software for measurement control and data acquisition

Basic communication architecture:

```text
                  PC / Python
                       |
                       | USB Serial
                       v
                     ESP32
                +------+------+
                |             |
                v             v
        Electrode MUX      ADMX2001
                |             |
                +------+------+
                       |
                       v
                Measurement Object
                       |
                       v
                Measurement Data
```

## Features

- Serial communication with ESP32 and ADMX2001
- Automatic serial-port selection
- Direct ADMX2001 command interface
- Electrode multiplexer control
- Adjacent measurement pattern
- Opposite measurement pattern
- Dual-ring electrode support
- Complex impedance measurements
- Frequency sweeps
- Configurable frequency-list measurements
- Automated long-term measurement sequences
- Environmental data acquisition
- JSON measurement logging
- Automatic ADMX2001 calibration
- Calibration profile save/load support
- EIT and impedance analysis tools

## Project Structure

```text
eit-host/
|
├── analysis/
│   ├── adjacent_analysis.py
│   ├── eit_reconstruction.py
│   ├── measurement_viewer.py
│   └── sweep_analysis.py
|
├── calibration_profiles/
|
├── config/
│   ├── settings.json
│   ├── calibration_frequencies_full.json
│   └── calibration_frequencies_1mhz_10mhz.json
|
├── data/
|
├── docs/
|
├── legacy/
|
├── src/
│   └── admx_eit/
│       ├── __init__.py
│       ├── acquisition.py
│       ├── calibration.py
│       ├── experiment.py
│       ├── logging_utils.py
│       ├── patterns.py
│       ├── protocol.py
│       └── terminal.py
|
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd eit-host
```

### 2. Create a virtual environment

Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install the project

```bash
python -m pip install -e .
```

The editable installation allows modifications inside `src/admx_eit/` to take effect without reinstalling the package.

## Configuration

The main configuration is stored in:

```text
config/settings.json
```

Example:

```json
{
  "measurement": {
    "mode": "normal",
    "output_file": "data/messungen.json"
  },
  "calibration": {
    "frequency_file": "config/calibration_frequencies_full.json",
    "profile_directory": "calibration_profiles"
  },
  "auto": {
    "duration_seconds": 3600,
    "wait_seconds": 20
  },
  "serial": {
    "baud": 115200,
    "timeout": 0.05
  }
}
```

### Measurement settings

`mode`

Default measurement mode used for single measurements.

Typical value:

```json
"mode": "normal"
```

`output_file`

Location of the generated measurement database:

```json
"output_file": "data/messungen.json"
```

### Calibration settings

`frequency_file`

Defines the frequency list used for frequency measurements and calibration.

Example:

```json
"frequency_file": "config/calibration_frequencies_full.json"
```

`profile_directory`

Directory used for saved calibration profiles.

### Automatic measurement settings

`duration_seconds`

Total duration of an automatic measurement experiment.

For example:

```json
"duration_seconds": 3600
```

corresponds to one hour.

`wait_seconds`

Waiting time between complete automatic measurement cycles.

### Serial settings

Default serial communication settings:

```json
"baud": 115200,
"timeout": 0.05
```

## Starting the Host

Start the interactive terminal with:

```bash
python -m admx_eit.terminal
```

Available serial ports are detected automatically:

```text
Gefundene Ports:
  1: COM9 (Silicon Labs CP210x USB to UART Bridge)

Port-Nummer wählen:
```

The port can also be specified directly:

```bash
python -m admx_eit.terminal --port COM9
```

Serial parameters can optionally be overridden:

```bash
python -m admx_eit.terminal --port COM9 --baud 115200 --timeout 0.05
```

## Terminal Commands

### ADMX2001 identification

```text
*idn?
```

Queries information about the connected ADMX2001.

### Single impedance measurement

```text
z
```

Executes an ADMX2001 impedance measurement.

A typical response has the form:

```text
0,8.914156e+03,-4.521209e+02
```

The host software stores the two measurement components together for further complex-value analysis.

### Environmental measurement

```text
env
```

Requests environmental sensor data from the ESP32.

Example response:

```text
ENV T=23.50 RH=45.20
```

### Display current electrode configuration

```text
elshow
```

Example:

```text
EL HCUR=S1 LCUR=S2 HPOT=S1 LPOT=S2
```

### Set electrodes

Syntax:

```text
el HCUR LCUR HPOT LPOT
```

Example:

```text
el 1 4 1 4
```

This configures:

```text
HCUR = electrode 1
LCUR = electrode 4
HPOT = electrode 1
LPOT = electrode 4
```

### Save a single measurement

```text
save
```

Performs a measurement and stores the result in the configured JSON measurement file.

### Adjacent measurement – Ring 1

```text
adj
```

Runs the adjacent measurement pattern using electrodes 1–8.

For every measurement point, the host:

1. switches the electrode multiplexer,
2. verifies the MUX response,
3. performs the ADMX2001 measurement,
4. parses the measurement result,
5. stores the MUX configuration and measurement data.

### Adjacent measurement – Ring 2

```text
adj2
```

Runs the corresponding adjacent pattern using electrodes 9–16.

### Opposite measurement pattern

```text
opp
```

Runs the opposite electrode measurement pattern.

### Frequency-list measurement

```text
savefreq
```

Performs one measurement for every configured frequency in the calibration frequency file.

The resulting measurements are stored as a single frequency-dependent run.

## Automatic Measurement

Start an automatic experiment using:

```text
auto
```

The experiment duration and waiting time are read from:

```text
config/settings.json
```

The automatic sequence is:

```text
Frequency Sweep Ring 1
        |
        v
Frequency Sweep Ring 2
        |
        v
Disable Sweep Mode
        |
        v
Adjacent Measurement Ring 1
        |
        v
Adjacent Measurement Ring 2
        |
        v
Wait
        |
        v
Next Cycle
```

The current sweep electrode configurations are:

```text
Ring 1: electrodes 1 and 5
Ring 2: electrodes 9 and 13
```

The normal adjacent measurements are currently configured at:

```text
8500 kHz
```

The automatic experiment can be stopped using:

```text
Ctrl+C
```

A complete measurement cycle is allowed to finish before the total experiment duration is evaluated.

## Calibration

### Automatic calibration

```text
autocalib
```

Runs the automatic ADMX2001 calibration procedure over the configured calibration frequencies.

The procedure includes:

```text
Open calibration
Short calibration
47 Ohm reference calibration
Calibration commit
```

### Save calibration profile

```text
savecal <name>
```

Example:

```text
savecal default
```

Reads the calibration coefficients from the ADMX2001 and stores them as a calibration profile.

### Load calibration profile

```text
loadcal <name>
```

Example:

```text
loadcal default
```

Loads the stored calibration coefficients back into the ADMX2001.

> **Note:** Calibration commands should only be used when the required calibration setup and reference impedances are correctly connected.

## Measurement Data

Measurement runs are stored in JSON format.

A run contains information such as:

```text
run_id
pattern
measurement_mode
start_timestamp
start_env
end_timestamp
end_env
measurements
```

Each EIT measurement point can additionally contain its MUX configuration:

```json
{
  "point": 1,
  "mux": {
    "cur_hi": 1,
    "cur_lo": 2,
    "pot_hi": 3,
    "pot_lo": 4
  },
  "samples": []
}
```

This ensures that measurement values remain associated with the physical electrode configuration used during acquisition.

## Analysis

Analysis tools are located in:

```text
analysis/
```

The current tools include:

### Measurement Viewer

```bash
python analysis/measurement_viewer.py
```

Provides graphical inspection of measurement runs including:

- real and imaginary components,
- magnitude and phase,
- Nyquist representation,
- Smith representation,
- measurement-point comparison.

### Adjacent Analysis

```text
analysis/adjacent_analysis.py
```

Used to compare adjacent-pattern measurements between selected experiment cycles.

### Sweep Analysis

```text
analysis/sweep_analysis.py
```

Used to compare frequency sweeps between experiment cycles.

### EIT Reconstruction

```text
analysis/eit_reconstruction.py
```

Provides a qualitative time-difference EIT reconstruction based on the adjacent measurements.

The reconstruction currently uses a simplified circular 2D resistive forward model and regularized inversion.

> The resulting EIT images represent qualitative relative changes. They must not be interpreted as absolutely calibrated conductivity distributions.

## Current Hardware Configuration

The current experimental system uses two electrode rings:

```text
Ring 1
Electrodes 1–8

Ring 2
Electrodes 9–16
```

The two rings are currently evaluated independently for the 2D EIT reconstruction.

A combined 3D reconstruction using both electrode planes is not yet implemented.

## Tested Functionality

The following functionality has been tested with the physical ESP32/ADMX2001 measurement setup after restructuring the host software:

- Python package installation
- Interactive terminal
- Serial communication
- ESP32 communication
- ADMX2001 communication
- ADMX2001 identification
- Electrode multiplexer control
- Single impedance measurements
- JSON measurement logging
- Adjacent measurement Ring 1
- Adjacent measurement Ring 2
- Frequency-list measurements
- Automatic measurement sequence
- Measurement viewer

## Known Issues / Work in Progress

- Environmental sensor values still require verification.
- Calibration functionality has not yet been fully revalidated after the host-software restructuring.
- EIT reconstruction currently uses a simplified qualitative 2D forward model.
- The two electrode rings are reconstructed independently.
- Further validation of the physical interpretation and calibration of the complex ADMX2001 measurement values is planned.

## Development

After modifying the source code:

```bash
git status
git add .
git commit -m "Describe the change"
git push
```

Because the package is installed in editable mode, changes inside:

```text
src/admx_eit/
```

are immediately available during development.

## Status

This repository currently represents a research prototype for automated impedance and EIT measurements using the ADMX2001 and an ESP32-controlled electrode multiplexer.

The software and reconstruction methods are under active development and should currently be considered experimental.
