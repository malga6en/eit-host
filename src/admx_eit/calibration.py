from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from .protocol import SerialBridge

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = PROJECT_ROOT / "config" / "settings.json"

with SETTINGS_FILE.open("r", encoding="utf-8") as f:
    SETTINGS = json.load(f)

CALIBRATION_FREQUENCY_FILE = (
    PROJECT_ROOT / SETTINGS["calibration"]["frequency_file"]
)

CALIBRATION_PROFILE_DIR = (
    PROJECT_ROOT / SETTINGS["calibration"]["profile_directory"]
)


AC_CALIBRATION_COEFFICIENTS = (
    "Ro", "Xo", "Go", "Bo", "Rs", "Xs", "Gs", "Bs", "Rg", "Xg", "Gg", "Bg",
)
DC_CALIBRATION_COEFFICIENTS = ("Rdg", "Rdo")
CALIBRATION_COEFFICIENTS = AC_CALIBRATION_COEFFICIENTS + DC_CALIBRATION_COEFFICIENTS
CALIBRATION_COEFFICIENT_RE = re.compile(
    r"^\s*(Ro|Xo|Go|Bo|Rs|Xs|Gs|Bs|Rg|Xg|Gg|Bg|Rdg|Rdo)\s*=\s*"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*$"
)
VOLT_GAIN_RE = re.compile(r"^\s*voltGain\s*=\s*([0-3])\s*$", re.MULTILINE)
CURR_GAIN_RE = re.compile(r"^\s*currGain\s*=\s*([0-3])\s*$", re.MULTILINE)

def load_calibration_frequencies(path: Path) -> list[float]:
    """Load and validate the frequencies used by the autocalib command."""
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Frequenzdatei nicht gefunden: {path}") from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Frequenzdatei kann nicht gelesen werden: {path}") from exc

    frequencies = data.get("frequencies") if isinstance(data, dict) else None
    if not isinstance(frequencies, list) or not frequencies:
        raise RuntimeError(
            "Die Frequenzdatei muss eine nicht leere Liste unter "
            "'frequencies' enthalten."
        )

    validated: list[float] = []
    for index, frequency in enumerate(frequencies, start=1):
        if isinstance(frequency, bool) or not isinstance(frequency, (int, float)):
            raise RuntimeError(f"Frequenz {index} ist keine Zahl: {frequency!r}")
        if frequency <= 0:
            raise RuntimeError(f"Frequenz {index} muss größer als 0 sein: {frequency}")
        validated.append(float(frequency))

    return validated

def format_frequency(frequency: float) -> str:
    """Avoid sending integer frequencies with an unnecessary decimal point."""
    return str(int(frequency)) if frequency.is_integer() else format(frequency, "g")

def calibration_profile_path(profile_name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", profile_name):
        raise RuntimeError(
            "Profilname darf nur Buchstaben, Zahlen, '-' und '_' enthalten."
        )
    return CALIBRATION_PROFILE_DIR / f"{profile_name}.json"

def extract_calibration_coefficients(text: str) -> dict[str, float]:
    coefficients: dict[str, float] = {}

    for raw_line in text.splitlines():
        match = CALIBRATION_COEFFICIENT_RE.match(raw_line)
        if match:
            coefficients[match.group(1)] = float(match.group(2))

    # The 12 AC coefficients are required. Rdg/Rdo are DC coefficients and
    # are absent from rdcal output on firmware/configurations without DC cal.
    missing = [name for name in AC_CALIBRATION_COEFFICIENTS if name not in coefficients]
    if missing:
        raise RuntimeError(
            "Unvollständige rdcal-Antwort; fehlende Koeffizienten: "
            + ", ".join(missing)
        )

    return {
        name: coefficients[name]
        for name in CALIBRATION_COEFFICIENTS
        if name in coefficients
    }

def read_active_gains(bridge: SerialBridge) -> tuple[int, int]:
    raw = bridge.send_admx("setgain", timeout=30.0)
    text = raw.decode("utf-8", errors="replace")
    voltage_match = VOLT_GAIN_RE.search(text)
    current_match = CURR_GAIN_RE.search(text)
    if voltage_match is None or current_match is None:
        raise RuntimeError("voltGain/currGain konnten nicht ausgelesen werden.")
    return int(voltage_match.group(1)), int(current_match.group(1))

def save_calibration_profile(
    bridge: SerialBridge,
    profile_name: str,
    frequency_file: Path = CALIBRATION_FREQUENCY_FILE,
) -> None:
    frequencies = load_calibration_frequencies(frequency_file)
    profile_path = calibration_profile_path(profile_name)
    frequency_sets = []
    voltage_gain, current_gain = read_active_gains(bridge)

    print(
        f"[SAVECAL] Sichere Profil {profile_name!r}: "
        f"{len(frequencies)} Frequenzen, "
        f"Gain {voltage_gain}/{current_gain}."
    )

    for frequency_index, frequency in enumerate(frequencies, start=1):
        frequency_text = format_frequency(frequency)
        print(
            f"\n[SAVECAL] Frequenz {frequency_index}/{len(frequencies)}: "
            f"{frequency_text} kHz"
        )

        bridge.send_admx(f"frequency {frequency_text}", timeout=30.0)
        bridge.send_admx("calibrate reload", timeout=30.0)

        gain_key = f"{voltage_gain}_{current_gain}"
        print(f"[SAVECAL] rdcal {voltage_gain} {current_gain}")
        raw = bridge.send_admx(
            f"rdcal {voltage_gain} {current_gain}",
            timeout=30.0,
        )
        gains = {
            gain_key: extract_calibration_coefficients(
                raw.decode("utf-8", errors="replace")
            )
        }

        frequency_sets.append(
            {
                "frequency_khz": frequency,
                "gains": gains,
            }
        )

    profile = {
        "format_version": 1,
        "profile_name": profile_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "frequencies": frequency_sets,
    }

    profile_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = profile_path.with_suffix(profile_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(profile, file, indent=2, ensure_ascii=False)
        file.write("\n")
    tmp_path.replace(profile_path)

    print(f"\n[SAVECAL] Profil gespeichert: {profile_path}")

def load_calibration_profile(
    bridge: SerialBridge,
    profile_name: str,
) -> None:
    profile_path = calibration_profile_path(profile_name)
    try:
        with profile_path.open("r", encoding="utf-8") as file:
            profile = json.load(file)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Kalibrierprofil nicht gefunden: {profile_path}") from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Kalibrierprofil kann nicht gelesen werden: {profile_path}") from exc

    frequency_sets = profile.get("frequencies") if isinstance(profile, dict) else None
    if not isinstance(frequency_sets, list) or not frequency_sets:
        raise RuntimeError("Kalibrierprofil enthält keine Frequenzsätze.")

    print(
        f"[LOADCAL] Lade Profil {profile_name!r} mit "
        f"{len(frequency_sets)} Frequenzpunkten."
    )
    print("[LOADCAL] Vorhandene Benutzerkalibrierungen werden überschrieben.")

    for frequency_index, frequency_set in enumerate(frequency_sets, start=1):
        if not isinstance(frequency_set, dict):
            raise RuntimeError(f"Ungültiger Frequenzsatz {frequency_index}.")

        try:
            frequency = float(frequency_set["frequency_khz"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Ungültige Frequenz in Satz {frequency_index}.") from exc

        gains = frequency_set.get("gains")
        if not isinstance(gains, dict):
            raise RuntimeError(f"Gain-Daten fehlen bei {frequency} kHz.")

        frequency_text = format_frequency(frequency)
        print(
            f"\n[LOADCAL] Frequenz {frequency_index}/{len(frequency_sets)}: "
            f"{frequency_text} kHz"
        )
        bridge.send_admx(f"frequency {frequency_text}", timeout=30.0)

        for gain_key, coefficients in gains.items():
            gain_match = re.fullmatch(r"([0-3])_([0-3])", gain_key)
            if gain_match is None or not isinstance(coefficients, dict):
                raise RuntimeError(
                    f"Ungültige Gain-Daten bei {frequency_text} kHz: {gain_key!r}."
                )
            voltage_gain = int(gain_match.group(1))
            current_gain = int(gain_match.group(2))

            print(f"[LOADCAL] Gain {voltage_gain}/{current_gain}")
            missing_ac = [
                name
                for name in AC_CALIBRATION_COEFFICIENTS
                if name not in coefficients
            ]
            if missing_ac:
                raise RuntimeError(
                    f"AC-Koeffizienten fehlen bei {frequency_text} kHz, "
                    f"Gain {gain_key}: {', '.join(missing_ac)}"
                )

            for coefficient_name in CALIBRATION_COEFFICIENTS:
                if coefficient_name not in coefficients:
                    continue
                try:
                    coefficient_value = float(coefficients[coefficient_name])
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        f"Koeffizient {coefficient_name} fehlt bei "
                        f"{frequency_text} kHz, Gain {gain_key}."
                    ) from exc

                bridge.send_admx(
                    f"storecal {voltage_gain} {current_gain} "
                    f"{coefficient_name} {coefficient_value:.17g}",
                    timeout=30.0,
                )

        print(f"[LOADCAL] Commit {frequency_text} kHz")
        bridge.send_admx("calibrate commit", timeout=60.0)

    print(f"\n[LOADCAL] Profil {profile_name!r} vollständig geladen.")

def run_automatic_calibration(
    bridge: SerialBridge,
    frequency_file: Path = CALIBRATION_FREQUENCY_FILE,
    wait_seconds: float = 4.0,
) -> None:
    frequencies = load_calibration_frequencies(frequency_file)

    print(
        f"[AUTOCALIB] Starte Kalibrierung für {len(frequencies)} "
        f"Frequenz(en) aus {frequency_file}."
    )
    print("[AUTOCALIB] Abbruch jederzeit mit Strg+C.")

    bridge.send_admx("average 200", timeout=30.0)

    for index, frequency in enumerate(frequencies, start=1):
        frequency_text = format_frequency(frequency)
        print(
            f"\n[AUTOCALIB] Frequenz {index}/{len(frequencies)}: "
            f"{frequency_text} kHz"
        )

        commands = (
            (f"frequency {frequency_text}", 0.0),
            ("calibrate open", wait_seconds),
            ("calibrate short", wait_seconds),
            ("calibrate rt 47", 0.0),
            # The ESP32 enters the password automatically; the completed
            # commit returns the regular ADMX prompt afterwards.
            ("calibrate commit", wait_seconds),
        )

        for command, delay_after in commands:
            print(f"[AUTOCALIB] {command}")
            bridge.send_admx(command, timeout=30.0)

            if delay_after > 0:
                print(f"[AUTOCALIB] Warte {delay_after:g} Sekunden ...")
                time.sleep(delay_after)

        print(f"[AUTOCALIB] {frequency_text} kHz abgeschlossen.")

    print(f"\n[AUTOCALIB] Alle {len(frequencies)} Frequenzen abgeschlossen.")
