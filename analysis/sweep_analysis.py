#!/usr/bin/env python3
"""
Frequenz-Sweeps ausgewaehlter Zyklen farbig ueberlagern.

python eit_viewer3.py messungen.json --output sweep_vergleich

"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


HUMIDIFIER_CYCLES = (0, 10, 20, 30, 40, 50, 59)
WATER_COMPARISON_CYCLES = (0, 10, 20, 30, 40, 50, 60, 61, 62)
PATTERNS = ("sweep_ring1", "sweep_ring2")


def load_sweep_runs(path: Path) -> dict[str, dict[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        root = json.load(handle)

    result: dict[str, dict[int, dict[str, Any]]] = {
        "sweep_ring1": {},
        "sweep_ring2": {},
    }

    for run in root.get("runs", []):
        pattern = str(run.get("pattern", ""))
        if pattern not in result:
            continue

        run_id = str(run.get("run_id", ""))
        try:
            cycle = int(run_id.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            continue

        result[pattern][cycle] = run

    return result


def sweep_values(run: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    measurements = run.get("measurements", [])
    if not measurements:
        raise ValueError(f"{run.get('run_id')}: Keine Messung vorhanden.")

    samples = measurements[0].get("samples", [])
    frequencies = []
    real_values = []
    imaginary_values = []

    for sample in samples:
        if "frequency" not in sample:
            continue
        values = sample.get("values", [])
        if len(values) < 2:
            continue

        frequencies.append(float(sample["frequency"]))
        real_values.append(float(values[0]))
        imaginary_values.append(float(values[1]))

    frequency = np.asarray(frequencies, dtype=float)
    real = np.asarray(real_values, dtype=float)
    imaginary = np.asarray(imaginary_values, dtype=float)
    magnitude = np.hypot(real, imaginary)

    order = np.argsort(frequency)
    return frequency[order], real[order], imaginary[order], magnitude[order]


def verify_cycles(
    runs: dict[str, dict[int, dict[str, Any]]],
    cycles: tuple[int, ...],
) -> None:
    for pattern in PATTERNS:
        missing = [cycle for cycle in cycles if cycle not in runs[pattern]]
        if missing:
            raise ValueError(f"{pattern}: Folgende Zyklen fehlen: {missing}")


def plot_comparison(
    output: Path,
    title: str,
    cycles: tuple[int, ...],
    runs: dict[str, dict[int, dict[str, Any]]],
    logarithmic_x: bool,
) -> None:
    fig, axes = plt.subplots(
        2,
        1,
        figsize=(14, 10),
        constrained_layout=True,
    )

    colors = plt.cm.turbo(np.linspace(0.04, 0.96, len(cycles)))

    for ax, pattern in zip(axes, PATTERNS):
        reference_frequency = None

        for color, cycle in zip(colors, cycles):
            frequency, _real, _imaginary, magnitude = sweep_values(
                runs[pattern][cycle]
            )

            if reference_frequency is None:
                reference_frequency = frequency
            elif (
                len(frequency) != len(reference_frequency)
                or not np.allclose(frequency, reference_frequency)
            ):
                raise ValueError(
                    f"{pattern}, Zyklus {cycle}: Frequenzraster stimmt "
                    "nicht mit der Referenz ueberein."
                )

            ax.plot(
                frequency,
                magnitude,
                color=color,
                linewidth=1.8,
                marker="o",
                markersize=2.8,
                label=f"Zyklus {cycle}",
            )

        if logarithmic_x:
            ax.set_xscale("log")

        ring_name = (
            "Sweep Ring 1 – Elektroden 1 und 5"
            if pattern == "sweep_ring1"
            else "Sweep Ring 2 – Elektroden 9 und 13"
        )
        ax.set_title(ring_name, fontweight="bold")
        ax.set_xlabel("Frequenz [Hz]")
        ax.set_ylabel(r"Betrag $|Z|$")
        ax.grid(True, which="both", alpha=0.35)
        ax.legend(
            title="Messzyklus",
            ncol=min(5, len(cycles)),
            fontsize=9,
            loc="best",
        )

    fig.suptitle(
        title + "\n" + r"$|Z|=\sqrt{\mathrm{Real}^2+\mathrm{Imaginär}^2}$",
        fontsize=16,
    )
    fig.savefig(output, dpi=180)
    plt.close(fig)


def write_csv(
    output: Path,
    runs: dict[str, dict[int, dict[str, Any]]],
    groups: dict[str, tuple[int, ...]],
) -> None:
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "group",
            "pattern",
            "cycle",
            "frequency_hz",
            "real",
            "imag",
            "magnitude",
        ])

        for group_name, cycles in groups.items():
            for pattern in PATTERNS:
                for cycle in cycles:
                    frequency, real, imaginary, magnitude = sweep_values(
                        runs[pattern][cycle]
                    )
                    for f, r, i, absolute in zip(
                        frequency,
                        real,
                        imaginary,
                        magnitude,
                    ):
                        writer.writerow([
                            group_name,
                            pattern,
                            cycle,
                            f,
                            r,
                            i,
                            absolute,
                        ])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sweep-Betraege mehrerer Messzyklen ueberlagern"
    )
    parser.add_argument(
        "json_file",
        type=Path,
        nargs="?",
        default=Path("messungen.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("sweep_vergleich"),
    )
    parser.add_argument(
        "--linear-frequency",
        action="store_true",
        help="Lineare statt logarithmischer Frequenzachse verwenden.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Abbildungen nach dem Speichern anzeigen.",
    )
    args = parser.parse_args()

    runs = load_sweep_runs(args.json_file)
    groups = {
        "humidifier": HUMIDIFIER_CYCLES,
        "water_comparison": WATER_COMPARISON_CYCLES,
    }

    for cycles in groups.values():
        verify_cycles(runs, cycles)

    args.output.mkdir(parents=True, exist_ok=True)

    humidifier_image = args.output / "sweeps_cycles_0_10_20_30_40_50_59.png"
    water_image = args.output / "sweeps_cycles_0_10_20_30_40_50_60_61_62.png"

    plot_comparison(
        humidifier_image,
        "Sweep-Vergleich – Verneblerphase",
        HUMIDIFIER_CYCLES,
        runs,
        logarithmic_x=not args.linear_frequency,
    )
    plot_comparison(
        water_image,
        "Sweep-Vergleich – einschließlich Wasserzyklen",
        WATER_COMPARISON_CYCLES,
        runs,
        logarithmic_x=not args.linear_frequency,
    )

    csv_path = args.output / "sweep_cycle_comparison.csv"
    write_csv(csv_path, runs, groups)

    print(f"Auswertung gespeichert in: {args.output.resolve()}")
    print(f"Erzeugt: {humidifier_image.name}")
    print(f"Erzeugt: {water_image.name}")
    print(f"Erzeugt: {csv_path.name}")

    if args.show:
        for image_path in (humidifier_image, water_image):
            image = plt.imread(image_path)
            fig, ax = plt.subplots(figsize=(13, 9))
            ax.imshow(image)
            ax.axis("off")
            fig.canvas.manager.set_window_title(image_path.name)
        plt.show()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())