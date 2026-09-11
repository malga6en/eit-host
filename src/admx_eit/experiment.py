from __future__ import annotations

import time
import json
from pathlib import Path

from .acquisition import run_pattern, run_save
from .logging_utils import JsonLogger
from .protocol import SerialBridge

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = PROJECT_ROOT / "config" / "settings.json"

with SETTINGS_FILE.open("r", encoding="utf-8") as f:
    SETTINGS = json.load(f)

AUTO_DURATION_SECONDS = float(
    SETTINGS["auto"]["duration_seconds"]
)

AUTO_WAIT_SECONDS = float(
    SETTINGS["auto"]["wait_seconds"]
)

def run_automatic_measurements(
    bridge: SerialBridge,
    logger: JsonLogger,
    duration_seconds: float = AUTO_DURATION_SECONDS,
    wait_seconds: float = AUTO_WAIT_SECONDS,
) -> None:
    """
    Wiederholt für die angegebene Dauer:

    1. Sweep Ring 1 mit Elektroden 1 und 5
    2. Sweep Ring 2 mit Elektroden 9 und 13
    3. Sweep-Modus ausschalten
    4. ADJ Ring 1 bei 8500 Hz
    5. ADJ Ring 2 bei 8500 Hz
    6. Warten
    """

    start_time = time.monotonic()
    end_time = start_time + duration_seconds
    cycle = 0

    print(
        f"[AUTO] Gestartet: Dauer={duration_seconds:.0f} s, "
        f"Wartezeit={wait_seconds:.0f} s"
    )
    print("[AUTO] Abbruch jederzeit mit Strg+C.")

    while time.monotonic() < end_time:
        cycle += 1

        print(f"\n========== Zyklus {cycle} ==========")

        try:
            # -----------------------------------------------------
            # 1. Sweep-Modus konfigurieren
            # -----------------------------------------------------
            sweep_commands = [
                "sweep_type frequency 0.2 10000",
                "count 100",
                "average 10",
            ]

            for command in sweep_commands:
                print(f"[AUTO] {command}")
                bridge.send_admx(command, timeout=15.0)

            # -----------------------------------------------------
            # 2. Sweep Ring 1: Elektroden 1 und 5
            # -----------------------------------------------------
            print("\n[AUTO] Sweep Ring 1: Elektroden 1 und 5")

            response = bridge.send_and_wait_for(
                "el 1 5 1 5",
                markers=("EL HCUR=", "ERR"),
                timeout=5.0,
            )

            if "ERR" in response:
                raise RuntimeError(
                    f"Sweep Ring 1 – Elektrodenfehler: "
                    f"{response.strip()}"
                )

            run_save(
                bridge,
                logger,
                measurement_mode="sweep",
                pattern="sweep_ring1",
            )

            # -----------------------------------------------------
            # 3. Sweep Ring 2: Elektroden 9 und 13
            # -----------------------------------------------------
            print("\n[AUTO] Sweep Ring 2: Elektroden 9 und 13")

            response = bridge.send_and_wait_for(
                "el 9 13 9 13",
                markers=("EL HCUR=", "ERR"),
                timeout=5.0,
            )

            if "ERR" in response:
                raise RuntimeError(
                    f"Sweep Ring 2 – Elektrodenfehler: "
                    f"{response.strip()}"
                )

            run_save(
                bridge,
                logger,
                measurement_mode="sweep",
                pattern="sweep_ring2",
            )

            # -----------------------------------------------------
            # 4. Sweep ausschalten und Einzelmessung konfigurieren
            # -----------------------------------------------------
            normal_commands = [
                "sweep_type off",
                "count 1",
                "average 5",
                "frequency 8500",
            ]

            for command in normal_commands:
                print(f"[AUTO] {command}")
                bridge.send_admx(command, timeout=15.0)

            # -----------------------------------------------------
            # 5. ADJ Ring 1: Elektroden 1–8
            # -----------------------------------------------------
            print("\n[AUTO] ADJ Ring 1: Elektroden 1–8")

            run_pattern(
                bridge,
                "adj",
                logger=logger,
                measurement_mode="normal",
            )

            # -----------------------------------------------------
            # 6. ADJ Ring 2: Elektroden 9–16
            # -----------------------------------------------------
            print("\n[AUTO] ADJ Ring 2: Elektroden 9–16")

            run_pattern(
                bridge,
                "adj2",
                logger=logger,
                measurement_mode="normal",
            )

        except (TimeoutError, RuntimeError) as exc:
            print(f"[AUTO][ERR] Zyklus {cycle}: {exc}")

        # ---------------------------------------------------------
        # 7. Prüfen, ob die Gesamtdauer erreicht wurde
        # ---------------------------------------------------------
        remaining_duration = end_time - time.monotonic()

        if remaining_duration <= 0:
            break

        # ---------------------------------------------------------
        # 8. Zwischen den vollständigen Zyklen warten
        # ---------------------------------------------------------
        actual_wait = min(wait_seconds, remaining_duration)

        print(
            f"\n[AUTO] Zyklus {cycle} beendet. "
            f"Warte {actual_wait:.1f} Sekunden ..."
        )

        time.sleep(actual_wait)

    elapsed = time.monotonic() - start_time

    print(
        f"\n[AUTO] Beendet nach {elapsed / 60:.1f} Minuten "
        f"und {cycle} Zyklen."
    )
