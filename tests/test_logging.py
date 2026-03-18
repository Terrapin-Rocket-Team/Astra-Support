from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from astra_support.sim.logging import write_sim_log


class LoggingTests(unittest.TestCase):
    def test_write_sim_log_includes_pressure_altitude_velocity_and_acceleration(self):
        history = {
            "time": [0.0, 1.0, 2.0],
            "sim_alt": [0.0, 10.0, 30.0],
            "sim_pressure_alt_m": [0.5, 10.5, 30.5],
            "sim_acc_mps2": [1.0, 2.0, 3.0],
            "fc_values": [["A"], ["B"], ["C"]],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "sim.csv"
            write_sim_log(log_path, history, ["FC_Stage"])
            with log_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(
            rows[0],
            ["Sim_Time", "Sim_Alt", "Sim_Pressure_Alt_MSL", "Sim_Vel_Z_mps", "Sim_Accel_Z_mps2", "FC_Stage"],
        )
        self.assertEqual(float(rows[1][1]), 0.0)
        self.assertEqual(float(rows[1][2]), 0.5)
        self.assertEqual(float(rows[1][3]), 10.0)
        self.assertEqual(float(rows[1][4]), 1.0)
        self.assertEqual(rows[1][5], "A")
