from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import serial


@dataclass
class SerialConfig:
    port: str
    baud: int = 115200
    timeout: float = 0.05
    write_timeout: float = 1.0


class SerialBridge:
    """Threaded serial bridge for PC <-> ESP32 communication."""

    ADMX_PROMPT = b"ADMX2001>"

    def __init__(self, config: SerialConfig):
        self.config = config
        self.ser = serial.Serial(
            port=config.port,
            baudrate=config.baud,
            timeout=config.timeout,
            write_timeout=config.write_timeout,
        )
        self._stop_event = threading.Event()
        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._lock = threading.Lock()
        self._rx_lock = threading.Lock()
        self._rx_condition = threading.Condition(self._rx_lock)
        self._rx_bytes = bytearray()
        self._rx_time = time.monotonic()

    def start(self) -> None:
        self._reader.start()

    def close(self) -> None:
        self._stop_event.set()
        with self._rx_condition:
            self._rx_condition.notify_all()
        try:
            self._reader.join(timeout=1.0)
        except Exception:
            pass
        try:
            self.ser.close()
        except Exception:
            pass

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                data = self.ser.read(self.ser.in_waiting or 1)
                if not data:
                    continue

                with self._rx_condition:
                    self._rx_bytes.extend(data)
                    self._rx_time = time.monotonic()
                    self._rx_condition.notify_all()

                # Terminalausgabe weiterhin direkt anzeigen.
                text = data.decode("utf-8", errors="replace")
                print(text, end="", flush=True)

            except serial.SerialException as e:
                print(f"\n[SERIAL ERROR] {e}")
                self._stop_event.set()
                with self._rx_condition:
                    self._rx_condition.notify_all()
                break
            except Exception as e:
                print(f"\n[READER ERROR] {e}")
                self._stop_event.set()
                with self._rx_condition:
                    self._rx_condition.notify_all()
                break

    def _write(self, line: str, eol: str = "\r\n") -> None:
        payload = (line + eol).encode("utf-8")
        with self._lock:
            self.ser.write(payload)
            self.ser.flush()

    def send(self, line: str, eol: str = "\r\n") -> None:
        """Send a command to the ESP32 without waiting for a response."""
        self._write(line, eol=eol)

    def _capture_start(self) -> int:
        with self._rx_lock:
            return len(self._rx_bytes)

    def _capture_slice(self, start_idx: int) -> bytes:
        with self._rx_lock:
            return bytes(self._rx_bytes[start_idx:])

    def send_admx(
        self,
        command: str,
        *,
        timeout: float = 15.0,
        marker: bytes = ADMX_PROMPT,
        eol: str = "\r\n",
    ) -> bytes:
        """Send an ADMX command via the ESP32 and wait for its ADMX prompt."""
        start_idx = self._capture_start()
        self._write(command, eol=eol)

        deadline = time.monotonic() + timeout

        while not self._stop_event.is_set():
            with self._rx_condition:
                response = bytes(self._rx_bytes[start_idx:])

                if marker in response:
                    return response

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"ADMX-Antwort auf {command!r} ohne Prompt "
                        f"{marker!r} erhalten."
                    )

                self._rx_condition.wait(timeout=remaining)

        raise RuntimeError("Serielle Verbindung wurde beendet.")

    def send_and_wait_for(
        self,
        line: str,
        *,
        markers: tuple[str, ...],
        timeout: float = 5.0,
        eol: str = "\r\n",
    ) -> str:
        """Send an ESP32 command and wait for one of the given text markers."""
        start_idx = self._capture_start()
        self._write(line, eol=eol)

        encoded_markers = tuple(marker.encode("utf-8") for marker in markers)
        deadline = time.monotonic() + timeout

        while not self._stop_event.is_set():
            with self._rx_condition:
                response = bytes(self._rx_bytes[start_idx:])

                if any(marker in response for marker in encoded_markers):
                    return response.decode("utf-8", errors="replace")

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Keine erwartete Antwort auf {line!r}: {markers!r}"
                    )

                self._rx_condition.wait(timeout=remaining)

        raise RuntimeError("Serielle Verbindung wurde beendet.")

    def snapshot(self) -> str:
        with self._rx_lock:
            return bytes(self._rx_bytes).decode("utf-8", errors="replace")
