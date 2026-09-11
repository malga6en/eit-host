from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
import json

from .calibration import CALIBRATION_FREQUENCY_FILE, format_frequency, load_calibration_frequencies
from .logging_utils import JsonLogger, extract_environment_values, extract_measurements
from .patterns import adjacent_pattern, opposite_pattern
from .protocol import SerialBridge

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = PROJECT_ROOT / "config" / "settings.json"

with SETTINGS_FILE.open("r", encoding="utf-8") as f:
    SETTINGS = json.load(f)

MEASUREMENT_MODE = SETTINGS["measurement"]["mode"]

CALIBRATION_FREQUENCY_FILE = (
    PROJECT_ROOT / SETTINGS["calibration"]["frequency_file"]
)

def read_environment(bridge: SerialBridge) -> tuple[float, float] | None:
    for attempt in range(3):
        try:
            raw = bridge.send_and_wait_for(
                "env",
                markers=("ENV ", "ENV ERR"),
                timeout=5.0,
            )
        except TimeoutError as exc:
            print(f"[WARN] ENV Timeout: {exc}")
            raw = ""

        env = extract_environment_values(raw)
        if env is not None:
            print(f"[ENV] T={env[0]:.2f} RH={env[1]:.2f}")
            return env

        print(f"[WARN] Keine ENV Werte gefunden. Versuch {attempt + 1}/3")
        time.sleep(0.3)

    return None

def run_save(
    bridge: SerialBridge,
    logger: JsonLogger,
    measurement_mode: str = "sweep",
    pattern: str = "single",
) -> None:

    print(
        f"[SAVE] Einzelmessung starten "
        f"(mode={MEASUREMENT_MODE})"
    )

    start_timestamp = datetime.now().isoformat(timespec="seconds")

    try:
        raw = bridge.send_admx(
            "z",
            timeout=30.0,
        )

    except (TimeoutError, RuntimeError) as exc:
        print(f"[ERR] ADMX: {exc}")
        return

    samples = extract_measurements(
        raw.decode(
            "utf-8",
            errors="replace",
        ),
        mode=measurement_mode,
    )

    if not samples:
        print("[WARN] Keine Messwerte gefunden.")
        return

    print(f"[SAVE] {len(samples)} Samples empfangen")

    end_timestamp = datetime.now().isoformat(timespec="seconds")

    measurements = [
        {
            "point": 1,
            "samples": samples,
        }
    ]

    saved_run_id = logger.write_run(
        pattern=pattern,
        measurement_mode=measurement_mode,
        start_timestamp=start_timestamp,
        start_env=None,
        end_timestamp=end_timestamp,
        end_env=None,
        measurements=measurements,
    )

    print(
        f"[SAVE] Gespeichert: {saved_run_id}"
    )

def run_frequency_list_measurement(
    bridge: SerialBridge,
    logger: JsonLogger,
    frequency_file: Path = CALIBRATION_FREQUENCY_FILE,
) -> None:
    """Measure once at every configured frequency and save one JSON run."""
    frequencies = load_calibration_frequencies(frequency_file)
    start_timestamp = datetime.now().isoformat(timespec="seconds")
    frequency_samples = []
    errors = []

    print(
        f"[SAVEFREQ] Starte {len(frequencies)} Einzelmessungen "
        f"aus {frequency_file}."
    )

    for command in ("average 10", "count 1"):
        print(f"[SAVEFREQ] {command}")
        bridge.send_admx(command, timeout=30.0)

    for point, frequency in enumerate(frequencies, start=1):
        frequency_text = format_frequency(frequency)
        print(
            f"\n[SAVEFREQ] Frequenz {point}/{len(frequencies)}: "
            f"{frequency_text} kHz"
        )

        try:
            bridge.send_admx(f"frequency {frequency_text}", timeout=30.0)
            raw = bridge.send_admx("z", timeout=30.0)
            samples = extract_measurements(
                raw.decode("utf-8", errors="replace"),
                mode="normal",
            )

            if not samples:
                raise RuntimeError("Keine Messwerte in der ADMX-Antwort gefunden.")

            # count 1 should return exactly one measurement line. Store the
            # configured frequency instead of the ADMX sample index so that
            # the result has the same shape as an ordinary sweep run.
            frequency_samples.append(
                {
                    # Configuration values are in kHz; sweep JSON data is
                    # stored in Hz for the existing viewer and data format.
                    "frequency": frequency * 1000.0,
                    "values": samples[0]["values"],
                }
            )
            print(f"[SAVEFREQ] {len(samples)} Sample(s) empfangen.")

        except (TimeoutError, RuntimeError) as exc:
            errors.append(
                {
                    "point": point,
                    "frequency_khz": frequency,
                    "error": str(exc),
                }
            )
            print(f"[SAVEFREQ][ERR] {frequency_text} kHz: {exc}")

    end_timestamp = datetime.now().isoformat(timespec="seconds")
    measurement = {
        "point": 1,
        "samples": frequency_samples,
    }
    if errors:
        measurement["errors"] = errors

    saved_run_id = logger.write_run(
        pattern="frequency_list",
        measurement_mode="sweep",
        start_timestamp=start_timestamp,
        start_env=None,
        end_timestamp=end_timestamp,
        end_env=None,
        measurements=[measurement],
    )

    print(
        f"\n[SAVEFREQ] Gespeichert: {saved_run_id} "
        f"({len(frequency_samples)}/{len(frequencies)} erfolgreich)"
    )

def run_pattern(
    bridge: SerialBridge,
    name: str,
    logger: JsonLogger | None = None,
    measurement_mode: str = "normal",
) -> None:

    if name == "adj":
        pairs = adjacent_pattern(8)
    elif name == "adj2":
        # Zweiter Elektrodenring: 9–16
        pairs = (
            (
                h_cur + 8,
                l_cur + 8,
                h_pot + 8,
                l_pot + 8,
            )
            for h_cur, l_cur, h_pot, l_pot in adjacent_pattern(8)
        )
    elif name == "opp":
        pairs = opposite_pattern(8)
    else:
        print(f"Unbekanntes Muster: {name}")
        return

    start_timestamp = datetime.now().isoformat(timespec="seconds")
    start_env = read_environment(bridge)

    time.sleep(0.2)

    measurements = []

    total = 0

    for h_cur, l_cur, h_pot, l_pot in pairs:
        total += 1

        print(
            f"\n[{total}] el "
            f"{h_cur} {l_cur} {h_pot} {l_pot}"
        )

        # ---------------------------------------------------------
        # 1. MUX schalten und auf Bestätigung des ESP32 warten
        # ---------------------------------------------------------
        mux_command = (
            f"el {h_cur} {l_cur} "
            f"{h_pot} {l_pot}"
        )

        try:
            mux_response = bridge.send_and_wait_for(
                mux_command,
                markers=("EL HCUR=", "ERR"),
                timeout=2.0,
            )

        except (TimeoutError, RuntimeError) as exc:
            print(f"[ERR] MUX keine Antwort: {exc}")
            continue

        # Fehler vom ESP32
        if "ERR" in mux_response:
            print(f"[ERR] MUX: {mux_response.strip()}")
            continue

        # Prüfen, ob die erwartete Konfiguration bestätigt wurde
        expected = (
            f"HCUR=S{h_cur} "
            f"LCUR=S{l_cur} "
            f"HPOT=S{h_pot} "
            f"LPOT=S{l_pot}"
        )

        if expected not in mux_response:
            print(
                "[ERR] MUX-Bestätigung stimmt nicht: "
                f"{mux_response.strip()}"
            )
            continue

        print(
            f"[MUX OK] "
            f"HCUR=S{h_cur} "
            f"LCUR=S{l_cur} "
            f"HPOT=S{h_pot} "
            f"LPOT=S{l_pot}"
        )

        # ---------------------------------------------------------
        # 2. Erst nach bestätigter MUX-Schaltung messen
        # ---------------------------------------------------------
        try:
            raw = bridge.send_admx(
                "z",
                timeout=1800.0,
            )

        except (TimeoutError, RuntimeError) as exc:
            print(f"[ERR] ADMX: {exc}")
            continue

        # ---------------------------------------------------------
        # 3. ADMX-Messwerte abhängig vom Messmodus parsen
        # ---------------------------------------------------------
        samples = extract_measurements(
            raw.decode(
                "utf-8",
                errors="replace",
            ),
            mode=measurement_mode,
        )

        if not samples:
            print("[WARN] Keine Messungen gefunden.")
            continue

        print(
            f"[MEAS] {len(samples)} Samples empfangen"
        )

        # ---------------------------------------------------------
        # 4. Messpunkt mit MUX-Konfiguration speichern
        # ---------------------------------------------------------
        measurements.append(
            {
                "point": total,
                "mux": {
                    "cur_hi": h_cur,
                    "cur_lo": l_cur,
                    "pot_hi": h_pot,
                    "pot_lo": l_pot,
                },
                "samples": samples,
            }
        )

    # -------------------------------------------------------------
    # 5. Umgebungsdaten am Ende
    # -------------------------------------------------------------
    end_timestamp = datetime.now().isoformat(timespec="seconds")
    end_env = read_environment(bridge)

    time.sleep(0.2)

    # -------------------------------------------------------------
    # 6. JSON speichern
    # -------------------------------------------------------------
    if logger is not None:
        saved_run_id = logger.write_run(
            pattern=name,
            measurement_mode=measurement_mode,
            start_timestamp=start_timestamp,
            start_env=start_env,
            end_timestamp=end_timestamp,
            end_env=end_env,
            measurements=measurements,
        )

        print(
            f"[DONE] {name} gespeichert: {saved_run_id}"
        )
