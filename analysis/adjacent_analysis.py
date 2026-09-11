#!/usr/bin/env python3
"""

ADJ-Betraege ausgewaehlter Messzyklen als untereinanderliegende Linienplots.

python eit_viewer2.py messungen.json --cycles 0 10 20 30 40 59 60 --output adj_betrag_auswertung              
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


DEFAULT_CYCLES = (0, 10, 20, 30, 40, 59, 62)


def load_runs(path: Path) -> dict[str, dict[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        root = json.load(handle)

    result: dict[str, dict[int, dict[str, Any]]] = {
        "adj": {},
        "adj2": {},
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


def magnitude_values(run: dict[str, Any]) -> np.ndarray:
    magnitudes = []

    for measurement in run.get("measurements", []):
        current_samples = measurement.get("samples", [])
        if not current_samples:
            magnitudes.append(np.nan)
            continue

        values = current_samples[0].get("values", [])
        if len(values) < 2:
            magnitudes.append(np.nan)
            continue

        real = float(values[0])
        imag = float(values[1])
        magnitudes.append(np.hypot(real, imag))

    return np.asarray(magnitudes, dtype=float)


def mux_label(measurement: dict[str, Any]) -> str:
    mux = measurement.get("mux") or {}
    return (
        f"{mux.get('cur_hi', '?')}-{mux.get('cur_lo', '?')} / "
        f"{mux.get('pot_hi', '?')}-{mux.get('pot_lo', '?')}"
    )


def plot_pattern(
    output: Path,
    pattern: str,
    selected_cycles: tuple[int, ...],
    pattern_runs: dict[int, dict[str, Any]],
    common_y_axis: bool,
) -> None:
    series = {
        cycle: magnitude_values(pattern_runs[cycle])
        for cycle in selected_cycles
    }

    point_count = len(series[selected_cycles[0]])
    if point_count == 0:
        raise ValueError(f"{pattern}: Keine Messpunkte vorhanden.")

    for cycle, values in series.items():
        if len(values) != point_count:
            raise ValueError(
                f"{pattern}, Zyklus {cycle}: {len(values)} statt "
                f"{point_count} Messpunkten."
            )

    points = np.arange(1, point_count + 1)
    all_values = np.concatenate(list(series.values()))
    finite_values = all_values[np.isfinite(all_values)]
    global_max = float(np.max(finite_values)) if finite_values.size else 1.0

    fig, axes = plt.subplots(
        len(selected_cycles),
        1,
        figsize=(15, 2.35 * len(selected_cycles)),
        sharex=True,
        sharey=common_y_axis,
        constrained_layout=True,
    )
    axes = np.atleast_1d(axes)

    colors = plt.cm.viridis(np.linspace(0.08, 0.92, len(selected_cycles)))

    for ax, color, cycle in zip(axes, colors, selected_cycles):
        values = series[cycle]
        ax.plot(
            points,
            values,
            color=color,
            linewidth=1.5,
            marker="o",
            markersize=3.5,
        )
        ax.fill_between(points, 0, values, color=color, alpha=0.12)
        ax.set_ylabel("|Z|")
        ax.set_title(f"Zyklus {cycle}", loc="left", fontweight="bold")
        ax.grid(True, alpha=0.35)
        ax.set_xlim(1, point_count)
        if common_y_axis:
            ax.set_ylim(0, global_max * 1.08)

    axes[-1].set_xlabel("ADJ-Messpaar / Messpunkt")
    axes[-1].set_xticks(points)
    axes[-1].tick_params(axis="x", labelsize=7)

    ring_title = (
        "Ring 1 – Elektroden 1 bis 8"
        if pattern == "adj"
        else "Ring 2 – Elektroden 9 bis 16"
    )
    fig.suptitle(
        f"ADJ-Betragswerte | {ring_title}\n"
        r"$|Z|=\sqrt{\mathrm{Real}^2+\mathrm{Imaginär}^2}$",
        fontsize=16,
    )
    fig.savefig(output, dpi=180)
    plt.close(fig)


def write_csv(
    output: Path,
    runs: dict[str, dict[int, dict[str, Any]]],
    selected_cycles: tuple[int, ...],
) -> None:
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "pattern",
            "cycle",
            "point",
            "current_pair",
            "voltage_pair",
            "real",
            "imag",
            "magnitude",
        ])

        for pattern in ("adj", "adj2"):
            for cycle in selected_cycles:
                run = runs[pattern][cycle]
                for point, measurement in enumerate(run.get("measurements", []), start=1):
                    mux = measurement.get("mux") or {}
                    current_samples = measurement.get("samples", [])
                    if current_samples and len(current_samples[0].get("values", [])) >= 2:
                        real, imag = map(float, current_samples[0]["values"][:2])
                        magnitude = float(np.hypot(real, imag))
                    else:
                        real = imag = magnitude = np.nan

                    writer.writerow([
                        pattern,
                        cycle,
                        point,
                        f"{mux.get('cur_hi', '?')}-{mux.get('cur_lo', '?')}",
                        f"{mux.get('pot_hi', '?')}-{mux.get('pot_lo', '?')}",
                        real,
                        imag,
                        magnitude,
                    ])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ADJ-Betraege ausgewaehlter Zyklen untereinander darstellen"
    )
    parser.add_argument(
        "json_file",
        type=Path,
        nargs="?",
        default=Path("messungen.json"),
    )
    parser.add_argument(
        "--cycles",
        type=int,
        nargs="+",
        default=list(DEFAULT_CYCLES),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("adj_betrag_auswertung"),
    )
    parser.add_argument(
        "--individual-y",
        action="store_true",
        help="Fuer jeden Zyklus eine eigene Y-Skalierung verwenden.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Bilder nach dem Speichern anzeigen.",
    )
    args = parser.parse_args()

    cycles = tuple(args.cycles)
    runs = load_runs(args.json_file)

    for pattern in ("adj", "adj2"):
        missing = [cycle for cycle in cycles if cycle not in runs[pattern]]
        if missing:
            raise ValueError(f"{pattern}: Folgende Zyklen fehlen: {missing}")

    args.output.mkdir(parents=True, exist_ok=True)
    generated_images = []

    for pattern, filename in (
        ("adj", "adj_ring1_magnitude_cycles.png"),
        ("adj2", "adj_ring2_magnitude_cycles.png"),
    ):
        image_path = args.output / filename
        plot_pattern(
            image_path,
            pattern,
            cycles,
            runs[pattern],
            common_y_axis=not args.individual_y,
        )
        generated_images.append(image_path)

    csv_path = args.output / "adj_magnitude_cycles.csv"
    write_csv(csv_path, runs, cycles)

    print(f"Auswertung gespeichert in: {args.output.resolve()}")
    for image_path in generated_images:
        print(f"Erzeugt: {image_path.name}")
    print(f"Erzeugt: {csv_path.name}")

    if args.show:
        for image_path in generated_images:
            image = plt.imread(image_path)
            fig, ax = plt.subplots(figsize=(12, 10))
            ax.imshow(image)
            ax.axis("off")
            fig.canvas.manager.set_window_title(image_path.name)
        plt.show()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())