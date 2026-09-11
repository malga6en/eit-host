#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import json

from serial.tools import list_ports

from .acquisition import run_frequency_list_measurement, run_pattern, run_save
from .calibration import load_calibration_profile, run_automatic_calibration, save_calibration_profile
from .experiment import run_automatic_measurements
from .logging_utils import JsonLogger
from .protocol import SerialBridge, SerialConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = PROJECT_ROOT / "config" / "settings.json"

with SETTINGS_FILE.open("r", encoding="utf-8") as f:
    SETTINGS = json.load(f)

JSON_FILE = PROJECT_ROOT / SETTINGS["measurement"]["output_file"]

DEFAULT_BAUD = int(SETTINGS["serial"]["baud"])
DEFAULT_TIMEOUT = float(SETTINGS["serial"]["timeout"])


def choose_port() -> str:
    ports = list(list_ports.comports())
    if not ports:
        raise RuntimeError("Keine seriellen Ports gefunden.")

    print("Gefundene Ports:")
    for i, p in enumerate(ports, start=1):
        print(f"  {i}: {p.device}  ({p.description})")

    while True:
        sel = input("Port-Nummer wählen: ").strip()
        if sel.isdigit():
            idx = int(sel)
            if 1 <= idx <= len(ports):
                return ports[idx - 1].device
        print("Ungültige Auswahl.")

def main() -> int:
    parser = argparse.ArgumentParser(description="ESP32 <-> ADMX2001 Terminal")
    parser.add_argument("--port", help="Serieller Port, z.B. COM5 oder /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200, help="Baudrate (default: 115200)")
    parser.add_argument("--timeout", type=float, default=0.05, help="Serial read timeout")
    args = parser.parse_args()

    port = args.port or choose_port()

    config = SerialConfig(
        port=port,
        baud=args.baud,
        timeout=args.timeout,
    )

    try:
        bridge = SerialBridge(config)
    except Exception as e:
        print(f"Kann Port nicht öffnen: {e}")
        return 1

    bridge.start()
    logger = JsonLogger(JSON_FILE)

    print(f"Verbunden mit {port} @ {args.baud}")
    print(
        "Befehle: el ... | elshow | z | env | *idn? | help | "
        "adj | adj2 | opp | save | savefreq | "
        "auto [dauer_s] [wartezeit_s] | autocalib | "
        "savecal <name> | loadcal <name> | exit"
    )

    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break
            except KeyboardInterrupt:
                break

            if not line:
                continue

            if line.lower() in ("exit", "quit", "q"):
                break

            if line.lower() == "auto":
                try:
                    # Keine Parameter übergeben:
                    # experiment.py verwendet die Werte aus settings.json
                    run_automatic_measurements(
                        bridge,
                        logger,
                    )

                except KeyboardInterrupt:
                    print("\n[AUTO] Durch Benutzer abgebrochen.")

                continue

            if line.lower() == "autocalib":
                try:
                    run_automatic_calibration(bridge)
                except KeyboardInterrupt:
                    print("\n[AUTOCALIB] Durch Benutzer abgebrochen.")
                except (TimeoutError, RuntimeError) as exc:
                    print(f"[AUTOCALIB][ERR] {exc}")
                continue

            if line.lower().startswith("savecal"):
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    print("[SAVECAL][ERR] Verwendung: savecal <profilname>")
                    continue
                try:
                    save_calibration_profile(bridge, parts[1].strip())
                except KeyboardInterrupt:
                    print("\n[SAVECAL] Durch Benutzer abgebrochen; kein Profil gespeichert.")
                except (TimeoutError, RuntimeError) as exc:
                    print(f"[SAVECAL][ERR] {exc}")
                continue

            if line.lower().startswith("loadcal"):
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    print("[LOADCAL][ERR] Verwendung: loadcal <profilname>")
                    continue
                try:
                    load_calibration_profile(bridge, parts[1].strip())
                except KeyboardInterrupt:
                    print("\n[LOADCAL] Durch Benutzer abgebrochen.")
                except (TimeoutError, RuntimeError) as exc:
                    print(f"[LOADCAL][ERR] {exc}")
                continue

            if line.lower() in ("adj", "adj2", "opp"):
                run_pattern(
                    bridge,
                    line.lower(),
                    logger=logger,
                    measurement_mode="normal",
                )
                continue

            if line.lower() == "save":
                run_save(
                    bridge,
                    logger,
                )
                continue

            if line.lower() == "savefreq":
                try:
                    run_frequency_list_measurement(
                        bridge,
                        logger,
                    )
                except KeyboardInterrupt:
                    print("\n[SAVEFREQ] Durch Benutzer abgebrochen.")
                except (TimeoutError, RuntimeError) as exc:
                    print(f"[SAVEFREQ][ERR] {exc}")
                continue

            lower_line = line.lower()

            # ESP32-eigene Kommandos: direkt senden, ohne auf ADMX2001> zu warten.
            if (
                lower_line.startswith("el ")
                or lower_line.startswith("set ")
                or lower_line in {
                    "elshow",
                    "show",
                    "mistshow",
                    "single",
                    "a",
                    "measure",
                    "b",
                    "c",
                    "calibrate commit",
                    "cal commit",
                }
                or lower_line.startswith("mist ")
            ):
                bridge.send(line)
                continue

            if lower_line == "env":
                try:
                    bridge.send_and_wait_for(
                        line,
                        markers=("ENV ", "ENV ERR"),
                        timeout=5.0,
                    )
                except (TimeoutError, RuntimeError) as exc:
                    print(f"[ERR] ESP32: {exc}")
                continue

            # Alles andere wird als ADMX-Befehl behandelt.
            try:
                bridge.send_admx(line, timeout=15.0)
            except (TimeoutError, RuntimeError) as exc:
                print(f"[ERR] ADMX: {exc}")

    finally:
        bridge.close()

    print("Beendet.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
