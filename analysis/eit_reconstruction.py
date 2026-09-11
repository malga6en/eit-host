#!/usr/bin/env python3
"""Qualitative 2D-Differenz-EIT fuer die ADJ-Runs zweier 8er-Ringe.

Zyklus 0 dient als Referenz. Eine Sensitivitaetsmatrix wird mit einem
kreisfoermigen 2D-Widerstandsnetz berechnet. Die Bilder zeigen daher eine
relative Leitfaehigkeits-Aenderung (Proxy), keine absolut kalibrierte Einheit.

python eit_viewer1.py messungen.json --cycles 0 10 20 30 40 50 60 --output eit_auswertung

python eit_viewer1.py messungen.json --cycles 59 60 61 62 --output eit_wasser
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import factorized


DEFAULT_CYCLES = (0, 10, 20, 30, 40, 50, 60)
VERSION = "3-components-1.0"


@dataclass
class ForwardModel:
    mask: np.ndarray
    x: np.ndarray
    y: np.ndarray
    node_index: np.ndarray
    coordinates: np.ndarray
    edges: np.ndarray
    electrodes: dict[int, int]
    solve: Any


def load_runs(path: Path) -> dict[str, dict[int, dict[str, Any]]]:
    root = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[int, dict[str, Any]]] = {"adj": {}, "adj2": {}}
    for run in root.get("runs", []):
        pattern = run.get("pattern")
        if pattern not in result:
            continue
        try:
            number = int(str(run["run_id"]).rsplit("_", 1)[1])
        except (KeyError, IndexError, ValueError):
            continue
        result[pattern][number] = run
    return result


def build_model(size: int = 45) -> ForwardModel:
    axis = np.linspace(-1.0, 1.0, size)
    x, y = np.meshgrid(axis, axis)
    mask = x * x + y * y <= 0.98**2
    node_index = np.full(mask.shape, -1, dtype=int)
    node_index[mask] = np.arange(np.count_nonzero(mask))
    coordinates = np.column_stack((x[mask], y[mask]))

    edges = []
    for row in range(size):
        for col in range(size):
            if not mask[row, col]:
                continue
            here = node_index[row, col]
            if col + 1 < size and mask[row, col + 1]:
                edges.append((here, node_index[row, col + 1]))
            if row + 1 < size and mask[row + 1, col]:
                edges.append((here, node_index[row + 1, col]))
    edge_array = np.asarray(edges, dtype=int)

    count = len(coordinates)
    laplacian = np.zeros((count, count), dtype=float)
    for a, b in edge_array:
        laplacian[a, a] += 1.0
        laplacian[b, b] += 1.0
        laplacian[a, b] -= 1.0
        laplacian[b, a] -= 1.0

    # Ein Referenzknoten entfernt die beliebige Potentialkonstante.
    ground = int(np.argmin(coordinates[:, 0] ** 2 + coordinates[:, 1] ** 2))
    keep = np.arange(count) != ground
    reduced_solver = factorized(csc_matrix(laplacian[np.ix_(keep, keep)]))

    def solve_current(source: int, sink: int) -> np.ndarray:
        rhs = np.zeros(count)
        rhs[source] = 1.0
        rhs[sink] = -1.0
        potential = np.zeros(count)
        potential[keep] = reduced_solver(rhs[keep])
        return potential

    # Elektrode 1 oben, Nummerierung im Uhrzeigersinn.
    electrodes: dict[int, int] = {}
    radii = np.linalg.norm(coordinates, axis=1)
    boundary_candidates = np.where(radii > 0.88)[0]
    for electrode in range(1, 9):
        angle = np.pi / 2 - 2 * np.pi * (electrode - 1) / 8
        target = np.array([0.96 * np.cos(angle), 0.96 * np.sin(angle)])
        candidate_coords = coordinates[boundary_candidates]
        nearest = np.argmin(np.sum((candidate_coords - target) ** 2, axis=1))
        electrodes[electrode] = int(boundary_candidates[nearest])

    model = ForwardModel(mask, x, y, node_index, coordinates, edge_array, electrodes, solve_current)
    return model


def local_electrode(number: int, pattern: str) -> int:
    return number if pattern == "adj" else number - 8


def measurement_vector(run: dict[str, Any]) -> np.ndarray:
    values = []
    for measurement in run.get("measurements", []):
        current_samples = measurement.get("samples", [])
        if not current_samples:
            values.append(complex(np.nan, np.nan))
            continue
        pair = current_samples[0].get("values", [])
        values.append(complex(float(pair[0]), float(pair[1])))
    return np.asarray(values, dtype=complex)


def sensitivity_matrix(model: ForwardModel, reference_run: dict[str, Any], pattern: str) -> np.ndarray:
    rows = []
    for measurement in reference_run.get("measurements", []):
        mux = measurement["mux"]
        cur_hi = model.electrodes[local_electrode(int(mux["cur_hi"]), pattern)]
        cur_lo = model.electrodes[local_electrode(int(mux["cur_lo"]), pattern)]
        pot_hi = model.electrodes[local_electrode(int(mux["pot_hi"]), pattern)]
        pot_lo = model.electrodes[local_electrode(int(mux["pot_lo"]), pattern)]

        drive = model.solve(cur_hi, cur_lo)
        adjoint = model.solve(pot_hi, pot_lo)
        model_voltage = drive[pot_hi] - drive[pot_lo]

        a = model.edges[:, 0]
        b = model.edges[:, 1]
        edge_sensitivity = -(drive[a] - drive[b]) * (adjoint[a] - adjoint[b])
        node_sensitivity = np.zeros(len(model.coordinates))
        np.add.at(node_sensitivity, a, edge_sensitivity * 0.5)
        np.add.at(node_sensitivity, b, edge_sensitivity * 0.5)

        # Relative Messdaten dV/V benoetigen ebenfalls eine relative Jacobian-Zeile.
        if abs(model_voltage) > 1e-12:
            node_sensitivity /= model_voltage
        rows.append(node_sensitivity)

    matrix = np.asarray(rows)
    norms = np.linalg.norm(matrix, axis=1)
    matrix /= np.where(norms > 0, norms, 1.0)[:, None]
    return matrix


def reconstruction_operator(jacobian: np.ndarray, regularization: float) -> np.ndarray:
    scale = np.trace(jacobian @ jacobian.T) / jacobian.shape[0]
    system = jacobian @ jacobian.T + regularization * scale * np.eye(jacobian.shape[0])
    return jacobian.T @ np.linalg.inv(system)


def reconstruct_series(
    runs: dict[int, dict[str, Any]],
    cycles: tuple[int, ...],
    jacobian: np.ndarray,
    operator: np.ndarray,
    component: str,
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    reference = measurement_vector(runs[cycles[0]])
    images = []
    data_changes = []
    for cycle in cycles:
        current = measurement_vector(runs[cycle])
        with np.errstate(divide="ignore", invalid="ignore"):
            relative_complex = (current - reference) / reference
            if component == "real":
                change = np.real(relative_complex)
            elif component == "imag":
                change = np.imag(relative_complex)
            elif component == "magnitude":
                change = (np.abs(current) - np.abs(reference)) / np.abs(reference)
            else:
                raise ValueError(f"Unbekannte Komponente: {component}")
        change[~np.isfinite(change)] = 0.0
        images.append(operator @ change)
        data_changes.append(change * 100.0)
    return images, data_changes


def image_grid(model: ForwardModel, values: np.ndarray, sigma: float) -> np.ndarray:
    grid = np.full(model.mask.shape, np.nan)
    raw = np.zeros(model.mask.shape)
    raw[model.mask] = values
    weights = gaussian_filter(model.mask.astype(float), sigma=sigma)
    smooth = gaussian_filter(raw, sigma=sigma) / np.maximum(weights, 1e-12)
    grid[model.mask] = smooth[model.mask]
    return grid


def plot_ring(
    output: Path,
    model: ForwardModel,
    pattern: str,
    cycles: tuple[int, ...],
    images: list[np.ndarray],
    data_changes: list[np.ndarray],
    sigma: float,
    component: str,
) -> None:
    grids = [image_grid(model, image, sigma) for image in images]
    finite = np.concatenate([grid[np.isfinite(grid)] for grid in grids[1:]])
    limit = float(np.percentile(np.abs(finite), 98)) if finite.size else 1.0
    limit = max(limit, 1e-12)

    fig, axes = plt.subplots(2, len(cycles), figsize=(3.2 * len(cycles), 6.4), constrained_layout=True)
    last_image = None
    for column, (cycle, grid, change) in enumerate(zip(cycles, grids, data_changes)):
        ax = axes[0, column]
        last_image = ax.imshow(
            grid, origin="lower", extent=(-1, 1, -1, 1), cmap="RdBu_r", vmin=-limit, vmax=limit
        )
        ax.set_title(f"Zyklus {cycle}\ngegen Zyklus {cycles[0]}")
        ax.set_aspect("equal")
        ax.axis("off")
        for electrode, node in model.electrodes.items():
            px, py = model.coordinates[node]
            label = electrode if pattern == "adj" else electrode + 8
            ax.text(px * 1.08, py * 1.08, str(label), ha="center", va="center", fontsize=9)

        bar = axes[1, column]
        bar.bar(np.arange(1, len(change) + 1), change, color=np.where(change >= 0, "tab:red", "tab:blue"))
        bar.axhline(0, color="black", linewidth=0.6)
        bar.set_title("Relative Messwertänderung")
        bar.set_xlabel("ADJ-Punkt")
        if column == 0:
            bar.set_ylabel("Re(ΔV/V₀) [%]")
        bar.grid(True, axis="y", alpha=0.3)

    ring_name = "Ring 1 (Elektroden 1-8)" if pattern == "adj" else "Ring 2 (Elektroden 9-16)"
    component_titles = {
        "real": "Realteil der relativen komplexen Änderung",
        "imag": "Imaginärteil der relativen komplexen Änderung",
        "magnitude": "Relative Betragsänderung",
    }
    component_labels = {
        "real": "Re(ΔZ/Z₀) [%]",
        "imag": "Im(ΔZ/Z₀) [%]",
        "magnitude": "Δ|Z|/|Z₀| [%]",
    }
    axes[1, 0].set_ylabel(component_labels[component])
    fig.suptitle(
        f"Zeitdifferentielle EIT – {ring_name}\n{component_titles[component]}",
        fontsize=16,
    )
    if last_image is not None:
        fig.colorbar(last_image, ax=axes[0, :].tolist(), shrink=0.75, label="relative Leitfähigkeitsänderung (a.u.)")
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Zeitdifferentielle EIT-Rekonstruktion")
    parser.add_argument("json_file", type=Path, nargs="?", default=Path("messungen.json"))
    parser.add_argument("--output", type=Path, default=Path("eit_auswertung"))
    parser.add_argument("--cycles", type=int, nargs="+", default=list(DEFAULT_CYCLES))
    parser.add_argument("--grid", type=int, default=45)
    parser.add_argument("--lambda", dest="regularization", type=float, default=0.08)
    parser.add_argument("--smooth", type=float, default=1.0)
    args = parser.parse_args()

    print(f"EIT-Auswerter Version: {VERSION}")

    cycles = tuple(args.cycles)
    if not cycles:
        raise ValueError("Mindestens ein Referenzzyklus muss angegeben werden.")
    runs = load_runs(args.json_file)
    for pattern in ("adj", "adj2"):
        missing = [cycle for cycle in cycles if cycle not in runs[pattern]]
        if missing:
            raise ValueError(f"{pattern}: Zyklen fehlen: {missing}")

    args.output.mkdir(parents=True, exist_ok=True)
    model = build_model(args.grid)
    for pattern, ring_name in (("adj", "ring1"), ("adj2", "ring2")):
        jacobian = sensitivity_matrix(model, runs[pattern][0], pattern)
        operator = reconstruction_operator(jacobian, args.regularization)
        for component in ("real", "imag", "magnitude"):
            images, changes = reconstruct_series(
                runs[pattern], cycles, jacobian, operator, component
            )
            plot_ring(
                args.output / f"eit_{ring_name}_{component}.png",
                model,
                pattern,
                cycles,
                images,
                changes,
                args.smooth,
                component,
            )
        np.save(args.output / f"jacobian_{pattern}.npy", jacobian)

    print(f"EIT-Auswertung gespeichert in: {args.output.resolve()}")
    print("Erzeugt: eit_ring1_real.png, eit_ring1_imag.png, eit_ring1_magnitude.png")
    print("Erzeugt: eit_ring2_real.png, eit_ring2_imag.png, eit_ring2_magnitude.png")
    print("Hinweis: qualitative Differenzbilder; Werte sind nicht absolut kalibriert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
