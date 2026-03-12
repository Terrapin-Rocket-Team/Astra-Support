from __future__ import annotations

import csv
from pathlib import Path


def write_sim_log(path: Path, history: dict[str, list], fc_header_names: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        header = ["Sim_Time", "Sim_Alt"]
        if fc_header_names:
            header.extend(fc_header_names)
        else:
            header.append("FC_Raw_Data")
        writer.writerow(header)
        for index, timestamp in enumerate(history["time"]):
            row = [timestamp, history["sim_alt"][index]]
            fc_values = history["fc_values"][index]
            if fc_header_names:
                row.extend(fc_values[: len(fc_header_names)])
                if len(fc_values) < len(fc_header_names):
                    row.extend([""] * (len(fc_header_names) - len(fc_values)))
            else:
                row.extend(fc_values)
            writer.writerow(row)
