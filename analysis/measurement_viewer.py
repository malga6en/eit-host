#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


DEFAULT_JSON = Path("messungen copy.json")


@dataclass
class MeasurementPoint:
    point: int
    mux: dict[str, Any]
    samples: list[dict[str, Any]]


@dataclass
class Run:
    run_id: str
    pattern: str
    measurement_mode: str
    start_timestamp: str
    end_timestamp: str
    start_env: dict[str, Any] | None
    end_env: dict[str, Any] | None
    measurements: list[MeasurementPoint]


class DataError(Exception):
    pass


def as_float(value: Any, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise DataError(f"Ungültiger Zahlenwert bei {name}: {value!r}") from exc


def load_runs(path: Path) -> list[Run]:
    if not path.exists():
        raise DataError(f"JSON-Datei nicht gefunden: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise DataError(f"Ungültiges JSON: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
        raise DataError("Erwartet wird ein JSON-Objekt mit einer Liste 'runs'.")

    result: list[Run] = []

    for run_raw in data["runs"]:
        if not isinstance(run_raw, dict):
            continue

        measurements: list[MeasurementPoint] = []
        for point_raw in run_raw.get("measurements", []):
            if not isinstance(point_raw, dict):
                continue

            samples: list[dict[str, Any]] = []
            for sample_raw in point_raw.get("samples", []):
                if not isinstance(sample_raw, dict):
                    continue

                values = sample_raw.get("values")
                if not isinstance(values, list) or len(values) < 2:
                    continue

                sample = dict(sample_raw)
                sample["values"] = [
                    as_float(values[0], "values[0]"),
                    as_float(values[1], "values[1]"),
                ]
                if "index" in sample:
                    try:
                        sample["index"] = int(sample["index"])
                    except (TypeError, ValueError):
                        pass
                if "frequency" in sample:
                    sample["frequency"] = as_float(sample["frequency"], "frequency")
                samples.append(sample)

            try:
                point_number = int(point_raw.get("point", len(measurements) + 1))
            except (TypeError, ValueError):
                point_number = len(measurements) + 1

            measurements.append(
                MeasurementPoint(
                    point=point_number,
                    mux=dict(point_raw.get("mux") or {}),
                    samples=samples,
                )
            )

        result.append(
            Run(
                run_id=str(run_raw.get("run_id", "")),
                pattern=str(run_raw.get("pattern", "")),
                measurement_mode=str(run_raw.get("measurement_mode", "normal")).lower(),
                start_timestamp=str(run_raw.get("start_timestamp", "")),
                end_timestamp=str(run_raw.get("end_timestamp", "")),
                start_env=run_raw.get("start_env"),
                end_env=run_raw.get("end_env"),
                measurements=measurements,
            )
        )

    return result


def complex_values(point: MeasurementPoint) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    indices = np.arange(len(point.samples), dtype=float)
    real = np.array([float(s["values"][0]) for s in point.samples], dtype=float)
    imag = np.array([float(s["values"][1]) for s in point.samples], dtype=float)
    return indices, real, imag


def frequency_values(point: MeasurementPoint) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frequencies = []
    real = []
    imag = []
    for sample in point.samples:
        if "frequency" not in sample:
            raise DataError("Sweep-Daten enthalten keine 'frequency'-Felder.")
        frequencies.append(float(sample["frequency"]))
        real.append(float(sample["values"][0]))
        imag.append(float(sample["values"][1]))
    return np.array(frequencies), np.array(real), np.array(imag)


def magnitude_phase(real: np.ndarray, imag: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    z = real + 1j * imag
    return np.abs(z), np.degrees(np.unwrap(np.angle(z)))


def mux_text(mux: dict[str, Any]) -> str:
    if not mux:
        return ""
    return (
        f"HCUR={mux.get('cur_hi', '?')}  "
        f"LCUR={mux.get('cur_lo', '?')}  "
        f"HPOT={mux.get('pot_hi', '?')}  "
        f"LPOT={mux.get('pot_lo', '?')}"
    )


def smith_gamma(real: np.ndarray, imag: np.ndarray, z0: float) -> np.ndarray:
    if z0 <= 0:
        raise DataError("Z0 muss größer als 0 sein.")
    z = real + 1j * imag
    return (z - z0) / (z + z0)


def draw_smith_grid(ax: Any) -> None:
    """Minimal Smith chart grid in reflection-coefficient coordinates."""
    ax.clear()
    theta = np.linspace(0, 2 * np.pi, 800)
    ax.plot(np.cos(theta), np.sin(theta), linewidth=0.8)

    # Constant resistance circles: center r/(r+1), radius 1/(r+1)
    for r in (0.2, 0.5, 1, 2, 5):
        center = r / (r + 1)
        radius = 1 / (r + 1)
        ax.plot(center + radius * np.cos(theta), radius * np.sin(theta), linewidth=0.45, alpha=0.6)

    # Constant reactance arcs: derived in gamma plane
    x_values = (0.2, 0.5, 1, 2, 5, -0.2, -0.5, -1, -2, -5)
    phi = np.linspace(-np.pi * 0.995, np.pi * 0.995, 1000)
    for x in x_values:
        # Circle center on imaginary axis: (1, 1/x), radius=|1/x|
        center_y = 1 / x
        radius = abs(1 / x)
        # Shift the sweep to cover the visible part of the circle.
        xx = 1 + radius * np.cos(phi)
        yy = center_y + radius * np.sin(phi)
        ax.plot(xx, yy, linewidth=0.35, alpha=0.45)

    ax.axhline(0, linewidth=0.5)
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.05, 1.05)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Re(Γ)")
    ax.set_ylabel("Im(Γ)")
    ax.set_title("Smith-Diagramm (normiert)")
    ax.grid(False)


class EITViewer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("EIT Measurement Viewer")
        self.geometry("1500x900")
        self.minsize(1200, 750)

        self.json_path = DEFAULT_JSON
        self.runs: list[Run] = []
        self.current_run: Run | None = None

        self.run_var = tk.StringVar()
        self.point_var = tk.StringVar(value="Alle Punkte")
        self.z0_var = tk.StringVar(value="50")
        self.status_var = tk.StringVar(value="Keine Datei geladen")
        self.info_var = tk.StringVar(value="")

        self._build_ui()
        self._load_initial_file()

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        ttk.Button(top, text="JSON öffnen", command=self.open_json).pack(side="left")
        ttk.Label(top, text="Run:").pack(side="left", padx=(18, 5))
        self.run_combo = ttk.Combobox(top, textvariable=self.run_var, state="readonly", width=26)
        self.run_combo.pack(side="left")
        self.run_combo.bind("<<ComboboxSelected>>", self.on_run_selected)

        ttk.Label(top, text="Messpunkt:").pack(side="left", padx=(18, 5))
        self.point_combo = ttk.Combobox(top, textvariable=self.point_var, state="readonly", width=18)
        self.point_combo.pack(side="left")
        self.point_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_plots())

        ttk.Label(top, text="Z0 [Ohm]:").pack(side="left", padx=(18, 5))
        ttk.Entry(top, textvariable=self.z0_var, width=8).pack(side="left")
        ttk.Button(top, text="Aktualisieren", command=self.update_plots).pack(side="left", padx=8)

        ttk.Label(top, textvariable=self.status_var).pack(side="right")

        info = ttk.Label(self, textvariable=self.info_var, padding=(10, 3), anchor="w")
        info.pack(fill="x")

        body = ttk.Frame(self, padding=(8, 0, 8, 8))
        body.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(body)
        self.notebook.pack(fill="both", expand=True)

        self.tabs: dict[str, tuple[Figure, FigureCanvasTkAgg]] = {}
        for name in self._tab_names():
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=name)
            fig = Figure(figsize=(8, 5), constrained_layout=True)
            canvas = FigureCanvasTkAgg(fig, master=frame)
            canvas.get_tk_widget().pack(fill="both", expand=True)
            self.tabs[name] = (fig, canvas)

        bottom = ttk.Frame(self, padding=(8, 0, 8, 8))
        bottom.pack(fill="x")
        ttk.Label(
            bottom,
            text="Hinweis: Ein Smith-Diagramm ist nur physikalisch sinnvoll, wenn die beiden Messwerte eine komplexe Impedanz/Admittanz mit geeigneter Normierung darstellen.",
            wraplength=1300,
        ).pack(anchor="w")

    @staticmethod
    def _tab_names() -> list[str]:
        return [
            "Real / Imaginär",
            "Betrag / Phase",
            "Nyquist",
            "Smith",
            "Vergleich",
        ]

    def _load_initial_file(self) -> None:
        if self.json_path.exists():
            try:
                self._load_file(self.json_path)
            except DataError as exc:
                self.status_var.set(str(exc))

    def open_json(self) -> None:
        filename = filedialog.askopenfilename(
            title="messungen.json auswählen",
            filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not filename:
            return
        try:
            self._load_file(Path(filename))
        except DataError as exc:
            messagebox.showerror("Fehler beim Laden", str(exc))

    def _load_file(self, path: Path) -> None:
        runs = load_runs(path)
        self.json_path = path
        self.runs = runs
        self.run_combo["values"] = [r.run_id for r in runs]
        self.status_var.set(f"{path}  |  {len(runs)} Runs")
        if runs:
            self.run_combo.current(0)
            self.on_run_selected()
        else:
            self.current_run = None
            self.point_combo["values"] = []
            self.point_var.set("Alle Punkte")
            self.info_var.set("Keine Runs in der Datei.")
            self.clear_plots()

    def on_run_selected(self, _event: Any = None) -> None:
        run_id = self.run_var.get()
        run = next((r for r in self.runs if r.run_id == run_id), None)
        self.current_run = run
        if run is None:
            return

        point_values = ["Alle Punkte"] + [f"Punkt {p.point}" for p in run.measurements]
        self.point_combo["values"] = point_values
        self.point_combo.current(0)

        env_text = ""
        if run.start_env:
            env_text = (
                f" | Start T={run.start_env.get('temperature_c', '?')} °C, "
                f"RH={run.start_env.get('humidity_rh', '?')} %"
            )
        self.info_var.set(
            f"Pattern={run.pattern} | Mode={run.measurement_mode} | "
            f"Messpunkte={len(run.measurements)} | "
            f"Start={run.start_timestamp} | Ende={run.end_timestamp}{env_text}"
        )
        self.update_plots()

    def selected_points(self, run: Run) -> list[MeasurementPoint]:
        selected = self.point_var.get()
        if selected == "Alle Punkte" or not selected:
            return run.measurements
        try:
            point_no = int(selected.split()[-1])
        except (ValueError, IndexError):
            return run.measurements
        return [p for p in run.measurements if p.point == point_no]

    def update_plots(self) -> None:
        run = self.current_run
        if run is None:
            self.clear_plots()
            return

        try:
            points = self.selected_points(run)
            self.plot_real_imag(run, points)
            self.plot_magnitude_phase(run, points)
            self.plot_nyquist(run, points)
            self.plot_smith(run, points)
            self.plot_comparison(run, points)
        except DataError as exc:
            messagebox.showerror("Darstellungsfehler", str(exc))

    def clear_plots(self) -> None:
        for fig, canvas in self.tabs.values():
            fig.clear()
            canvas.draw_idle()

    def point_label(self, point: MeasurementPoint) -> str:
        return f"Punkt {point.point} | {mux_text(point.mux)}"

    def plot_real_imag(self, run: Run, points: list[MeasurementPoint]) -> None:
        fig, canvas = self.tabs["Real / Imaginär"]
        fig.clear()

        ax_real = fig.add_subplot(211)
        ax_imag = fig.add_subplot(212)

        for point in points:
            x, real, imag = (
                frequency_values(point)
                if run.measurement_mode == "sweep"
                else complex_values(point)
            )
            if len(x) == 0:
                continue

            ax_real.plot(x, real, marker="o", markersize=3, label=f"P{point.point}")
            ax_imag.plot(x, imag, marker="o", markersize=3, label=f"P{point.point}")

        if run.measurement_mode == "sweep":
            ax_real.set_xscale("log")
            ax_imag.set_xscale("log")

        ax_real.set_title("Realteil")
        ax_real.set_ylabel("Real")
        ax_real.grid(True)
        ax_real.legend(fontsize=8)

        ax_imag.set_title("Imaginärteil")
        ax_imag.set_xlabel("Frequenz [Hz]" if run.measurement_mode == "sweep" else "Sample")
        ax_imag.set_ylabel("Imaginär")
        ax_imag.grid(True)
        ax_imag.legend(fontsize=8)

        canvas.draw_idle()

    def plot_magnitude_phase(self, run: Run, points: list[MeasurementPoint]) -> None:
        fig, canvas = self.tabs["Betrag / Phase"]
        fig.clear()
        ax1 = fig.add_subplot(211)
        ax2 = fig.add_subplot(212)

        for point in points:
            x, real, imag = (
                frequency_values(point) if run.measurement_mode == "sweep" else complex_values(point)
            )
            if len(x) == 0:
                continue
            magnitude, phase = magnitude_phase(real, imag)
            ax1.plot(x, magnitude, marker="o", markersize=3, label=f"P{point.point}")
            ax2.plot(x, phase, marker="o", markersize=3, label=f"P{point.point}")

        if run.measurement_mode == "sweep":
            ax1.set_xscale("log")
            ax2.set_xscale("log")

        ax1.set_title("Betrag")
        ax1.set_ylabel("|Z| / |Messwert|")
        ax1.grid(True)
        ax1.legend(fontsize=8)

        ax2.set_title("Phase")
        ax2.set_xlabel("Frequenz [Hz]" if run.measurement_mode == "sweep" else "Sample")
        ax2.set_ylabel("Phase [°]")
        ax2.grid(True)
        ax2.legend(fontsize=8)

        canvas.draw_idle()

    def plot_nyquist(self, run: Run, points: list[MeasurementPoint]) -> None:
        fig, canvas = self.tabs["Nyquist"]
        fig.clear()
        ax = fig.add_subplot(111)

        for point in points:
            _, real, imag = (
                frequency_values(point) if run.measurement_mode == "sweep" else complex_values(point)
            )
            if len(real) == 0:
                continue
            ax.plot(real, imag, marker="o", markersize=3, label=f"P{point.point}")

        ax.axhline(0, linewidth=0.6)
        ax.axvline(0, linewidth=0.6)
        ax.set_title("Nyquist-Diagramm")
        ax.set_xlabel("Real")
        ax.set_ylabel("Imaginär")
        ax.grid(True)
        ax.legend(fontsize=8)
        ax.set_aspect("equal", adjustable="datalim")
        canvas.draw_idle()

    def plot_smith(self, run: Run, points: list[MeasurementPoint]) -> None:
        fig, canvas = self.tabs["Smith"]
        fig.clear()
        ax = fig.add_subplot(111)
        draw_smith_grid(ax)

        try:
            z0 = float(self.z0_var.get())
        except ValueError as exc:
            raise DataError("Z0 muss eine gültige Zahl sein.") from exc

        for point in points:
            if run.measurement_mode == "sweep":
                _, real, imag = frequency_values(point)
            else:
                _, real, imag = complex_values(point)

            if len(real) == 0:
                continue

            gamma = np.asarray(
                smith_gamma(real, imag, z0),
                dtype=np.complex128,
            )

            ax.plot(
                np.real(gamma),
                np.imag(gamma),
                marker="o",
                markersize=3,
                label=f"P{point.point}",
            )
        ax.legend(fontsize=8)
        canvas.draw_idle()

    def plot_comparison(self, run: Run, points: list[MeasurementPoint]) -> None:
        fig, canvas = self.tabs["Vergleich"]
        fig.clear()
        ax = fig.add_subplot(111)

        for point in points:
            x, real, imag = (
                frequency_values(point) if run.measurement_mode == "sweep" else complex_values(point)
            )
            if len(x) == 0:
                continue
            magnitude, _phase = magnitude_phase(real, imag)
            ax.plot(x, magnitude, marker="o", markersize=3, label=f"P{point.point}")

        if run.measurement_mode == "sweep":
            ax.set_xscale("log")
            ax.set_xlabel("Frequenz [Hz]")
        else:
            ax.set_xlabel("Sample")

        ax.set_title("Vergleich der Messpunkte | Betrag")
        ax.set_ylabel("Betrag")
        ax.grid(True)
        ax.legend(fontsize=8)
        canvas.draw_idle()


def main() -> None:
    app = EITViewer()
    app.mainloop()


if __name__ == "__main__":
    main()