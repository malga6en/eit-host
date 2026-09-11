import serial
import time
import csv
import os
from datetime import datetime

PORT = "COM9"
BAUD = 115200
TIMEOUT = 1.0

N_POINTS = 40
OUTFILE = "eit_measurements.csv"


def read_measurement_run(ser):
    """
    Sendet measure an den ESP32 und liest alle MEAS-Zeilen bis DONE.
    Rückgabe: Liste mit 40 Einträgen, Index 0 = Punkt 1, ...
    """
    row = ["" for _ in range(N_POINTS)]

    ser.reset_input_buffer()
    ser.write(b"measure\r\n")
    ser.flush()

    while True:
        line = ser.readline().decode("utf-8", errors="replace").strip()

        if not line:
            continue

        print(line)

        if line == "START":
            continue

        if line == "DONE":
            break

        if line.startswith("MEAS "):
            # Format:
            # MEAS 1 CUR 1 2 POT 3 4 0,-8.902670e+05,-9.625352e+05
            parts = line.split(maxsplit=8)
            if len(parts) >= 9:
                point = int(parts[1])
                payload = parts[8]

                if 1 <= point <= N_POINTS:
                    row[point - 1] = payload

        elif line.startswith("ERR"):
            raise RuntimeError(line)

    return row


def append_row_to_csv(path, row):
    file_exists = os.path.exists(path)

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            header = ["run_id", "timestamp"] + [f"p{i}" for i in range(1, N_POINTS + 1)]
            writer.writerow(header)

        run_id = get_next_run_id(path)
        timestamp = datetime.now().isoformat(timespec="seconds")
        writer.writerow([run_id, timestamp] + row)


def get_next_run_id(path):
    """
    Einfacher Zähler: liest die vorhandenen Zeilen und setzt die nächste ID.
    """
    if not os.path.exists(path):
        return 1

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if len(lines) <= 1:
        return 1

    last = lines[-1].split(",", 1)[0]
    try:
        return int(last) + 1
    except ValueError:
        return 1


def main():
    with serial.Serial(PORT, BAUD, timeout=TIMEOUT) as ser:
        time.sleep(2.0)
        ser.reset_input_buffer()

        print("Verbunden. Tippe measure und Enter.")
        print("Jeder Lauf wird als neue Zeile in der CSV gespeichert.\n")

        while True:
            cmd = input("> ").strip()

            if not cmd:
                continue

            if cmd.lower() == "measure":
                row = read_measurement_run(ser)
                append_row_to_csv(OUTFILE, row)
                print(f"Gespeichert in {OUTFILE}\n")
            else:
                ser.write((cmd + "\r\n").encode("utf-8"))
                ser.flush()

                while True:
                    line = ser.readline().decode("utf-8", errors="replace").strip()
                    if not line:
                        break
                    print(line)


if __name__ == "__main__":
    main()