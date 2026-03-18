from __future__ import annotations

import csv
import math
from pathlib import Path


def write_sim_log(path: Path, history: dict[str, list], fc_header_names: list[str]) -> None:
    real_velocity = _derive_series_rate(history["time"], history["sim_alt"])
    real_accel = history["sim_acc_mps2"]
    if not any(_is_number(value) for value in real_accel):
        real_accel = _derive_series_rate(history["time"], real_velocity)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        header = ["Sim_Time", "Sim_Alt", "Sensor_Alt_AGL", "Sim_Vel_Z_mps", "Sim_Accel_Z_mps2", "Sensor_Accel_Z_mps2"]
        if fc_header_names:
            header.extend(fc_header_names)
        else:
            header.append("FC_Raw_Data")
        writer.writerow(header)
        for index, timestamp in enumerate(history["time"]):
            row = [
                timestamp,
                history["sim_alt"][index],
                history["sensor_alt_agl_m"][index],
                _nan_to_empty(real_velocity[index]) if index < len(real_velocity) else "",
                _nan_to_empty(real_accel[index]) if index < len(real_accel) else "",
                _nan_to_empty(history["sensor_acc_z_mps2"][index]) if index < len(history["sensor_acc_z_mps2"]) else "",
            ]
            fc_values = history["fc_values"][index]
            if fc_header_names:
                row.extend(fc_values[: len(fc_header_names)])
                if len(fc_values) < len(fc_header_names):
                    row.extend([""] * (len(fc_header_names) - len(fc_values)))
            else:
                row.extend(fc_values)
            writer.writerow(row)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not math.isnan(value)


def _nan_to_empty(value):
    if _is_number(value):
        return value
    return ""


def _derive_series_rate(time_values: list[float], sample_values: list[float]) -> list[float]:
    if not time_values or not sample_values:
        return []

    derived = [float("nan")] * min(len(time_values), len(sample_values))
    for index in range(1, len(derived)):
        prev_time = time_values[index - 1]
        curr_time = time_values[index]
        prev_value = sample_values[index - 1]
        curr_value = sample_values[index]
        if not (_is_number(prev_value) and _is_number(curr_value)):
            continue
        dt = curr_time - prev_time
        if dt <= 0:
            continue
        derived[index] = (curr_value - prev_value) / dt

    if len(derived) > 1 and _is_number(derived[1]):
        derived[0] = derived[1]
    return derived
