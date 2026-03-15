from __future__ import annotations

import math
import unittest
from unittest import mock

from astra_support.sim import plotting


class PlottingTests(unittest.TestCase):
    def test_plot_history_handles_velocity_and_acceleration_panels(self):
        history = {
            "time": [0.0, 0.5, 1.0],
            "sim_alt": [0.0, 10.0, 25.0],
            "sim_acc_mps2": [math.nan, 40.0, 30.0],
            "sensor_alt": [0.0, 10.0, 25.0],
            "fc_alt": [math.nan, 9.5, 24.0],
            "fc_stage": ["PAD", "BOOST", "COAST"],
            "fc_vel_z_mps": [math.nan, 18.0, 12.0],
            "fc_acc_z_mps2": [math.nan, 39.0, -9.0],
            "fc_flap_cmd_deg": [0.0, 2.0, 4.0],
            "fc_flap_actual_deg": [0.0, 1.5, 3.5],
            "fc_est_apogee_m": [math.nan, 120.0, 130.0],
            "fc_target_apogee_m": [150.0, 150.0, 150.0],
            "fc_mach": [0.0, 0.3, 0.5],
            "fc_values": [[], [], []],
        }

        with mock.patch.object(plotting.plt, "show") as patched_show:
            plotting.plot_history(history, source_name="airbrake")

        patched_show.assert_called_once()
