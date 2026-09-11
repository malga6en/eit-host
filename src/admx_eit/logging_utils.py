from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

ENV_RE = re.compile(
    r"^ENV\s+T=([-+]?\d+(?:\.\d+)?)\s+RH=([-+]?\d+(?:\.\d+)?)$"
)

# ADMX sample format seen in the real terminal output:
# 0,5.532045e+03,1.714710e+03
MEASUREMENT_RE = re.compile(
    r"^"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    r","
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    r","
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    r"$"
)


def extract_measurements(
    text: str,
    mode: str,
) -> list[dict[str, Any]]:
    """
    Parse ADMX measurement lines.

    normal:
        index,value1,value2

    sweep:
        frequency,value1,value2
    """

    if mode not in {"normal", "sweep"}:
        raise ValueError(
            f"Unbekannter Messmodus: {mode}"
        )

    measurements: list[dict[str, Any]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        match = MEASUREMENT_RE.match(line)

        if not match:
            continue

        first = float(match.group(1))
        value1 = float(match.group(2))
        value2 = float(match.group(3))

        if mode == "normal":
            measurements.append(
                {
                    "index": int(first),
                    "values": [
                        value1,
                        value2,
                    ],
                }
            )

        else:  # sweep
            measurements.append(
                {
                    "frequency": first,
                    "values": [
                        value1,
                        value2,
                    ],
                }
            )

    return measurements

def extract_environment_values(text: str) -> Optional[Tuple[float, float]]:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = ENV_RE.match(line)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None


@dataclass
class JsonLogger:
    path: Path

    def _load(self) -> dict[str, Any]:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return {"runs": []}

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"JSON-Datei kann nicht gelesen werden: {self.path}") from exc

        if not isinstance(data, dict):
            raise RuntimeError("Ungültiges JSON-Format: Root muss ein Objekt sein.")

        runs = data.get("runs")
        if runs is None:
            data["runs"] = []
        elif not isinstance(runs, list):
            raise RuntimeError("Ungültiges JSON-Format: 'runs' muss eine Liste sein.")

        return data

    def _next_run_id(self, pattern: str, runs: Sequence[dict[str, Any]]) -> str:
        prefix = f"{pattern}_"
        max_id = -1

        for run in runs:
            run_id = run.get("run_id") if isinstance(run, dict) else None
            if not isinstance(run_id, str) or not run_id.startswith(prefix):
                continue

            suffix = run_id[len(prefix):]
            if suffix.isdigit():
                max_id = max(max_id, int(suffix))

        return f"{pattern}_{max_id + 1}"

    def write_run(
        self,
        *,
        pattern: str,
        measurement_mode: str,
        start_timestamp: str,
        start_env: Optional[Tuple[float, float]],
        end_timestamp: str,
        end_env: Optional[Tuple[float, float]],
        measurements: Sequence[dict[str, Any]],
    ) -> str:
        data = self._load()
        runs = data["runs"]
        run_id = self._next_run_id(pattern, runs)

        run: dict[str, Any] = {
            "run_id": run_id,
            "pattern": pattern,
            "measurement_mode": measurement_mode,
            "start_timestamp": start_timestamp,
            "start_env": None,
            "end_timestamp": end_timestamp,
            "end_env": None,
            "measurements": list(measurements),
        }

        if start_env is not None:
            run["start_env"] = {
                "temperature_c": start_env[0],
                "humidity_rh": start_env[1],
            }

        if end_env is not None:
            run["end_env"] = {
                "temperature_c": end_env[0],
                "humidity_rh": end_env[1],
            }

        runs.append(run)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

        tmp_path.replace(self.path)
        return run_id