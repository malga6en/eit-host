# Architecture

```text
PC / Python
    |
    | USB serial
    v
ESP32 bridge
    |-- electrode multiplexer --> dual 8-electrode rings
    `-- ADMX2001 -------------> impedance measurement

Measurement acquisition
    -> JSON logging
    -> offline sweep/impedance analysis
    -> qualitative difference-EIT reconstruction
```

## Software modules

- `protocol.py`: threaded serial bridge and ADMX prompt handling.
- `patterns.py`: reusable adjacent/opposite electrode patterns.
- `logging_utils.py`: ADMX response parsing, environment parsing and JSON run logging.
- `terminal.py`: interactive CLI and command routing.
- `acquisition.py`: environment reads, single measurements, frequency-list measurements and electrode-pattern scans.
- `calibration.py`: calibration frequency handling, automatic calibration and calibration profile save/load.
- `experiment.py`: long-running automated measurement cycles.
