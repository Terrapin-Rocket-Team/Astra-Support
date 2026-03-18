from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from astra_support.sim import data_sources
from astra_support.sim import session


class SessionTests(unittest.TestCase):
    def test_run_simulation_wraps_custom_source_with_noise(self):
        class FinishedSim:
            def is_finished(self):
                return True

        args = SimpleNamespace(
            mode="sitl",
            host="localhost",
            tcp_port=5555,
            project=".",
            source="airbrake",
            no_auto_start=False,
            sitl_exe=None,
            sitl_log=None,
            show_sitl_output=False,
            build=False,
            header_probe="CMD/HEADER\n",
            ready_token="",
            ready_probe="",
            target_apogee=None,
            no_plot=True,
            rotate=False,
            rotation=None,
            noise=True,
            accel_noise=0.05,
            gyro_noise=0.01,
            mag_noise=0.5,
            baro_noise=0.5,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            with (
                mock.patch.object(session, "configure_console_output"),
                mock.patch.object(session, "_build_native_if_requested"),
                mock.patch.object(session, "load_custom_sim_hooks", return_value=(object(), None)),
                mock.patch.object(session, "_create_custom_sim", return_value=FinishedSim()),
                mock.patch.object(session, "_create_builtin_sim"),
                mock.patch.object(session, "TCPLink"),
                mock.patch.object(session, "_start_sitl_if_needed"),
                mock.patch.object(session, "_handshake", return_value=({}, ["Time"])),
                mock.patch.object(session, "write_sim_log"),
                mock.patch.object(session, "plot_history"),
                mock.patch.object(session.time, "strftime", return_value="20260101_000000"),
                mock.patch.object(session.data_sources, "NoisySim", side_effect=lambda sim, **_: sim) as noisy_sim,
            ):
                session.run_simulation(args, project_root)

        noisy_sim.assert_called_once()

    def test_apply_sim_wrappers_wraps_csv_source_with_noise(self):
        args = SimpleNamespace(
            source="airbrake.csv",
            udp_port=9000,
            rotate=False,
            rotation=None,
            noise=True,
            accel_noise=0.05,
            gyro_noise=0.01,
            mag_noise=0.5,
            baro_noise=0.5,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            csv_path = project_root / "airbrake.csv"
            csv_path.write_text("time,altitude\n0,0\n1,10\n", encoding="utf-8")

            base_sim = session._create_builtin_sim(args, project_root)
            sim = session._apply_sim_wrappers(base_sim, args)

        self.assertIsInstance(sim, data_sources.NoisySim)

    def test_run_simulation_listens_before_starting_sitl(self):
        events: list[str] = []

        class FakeTCPLink:
            def __init__(self, *args, **kwargs):
                events.append("listen")

            def wait_for_connection(self, connect_timeout_s=None, on_wait=None):
                events.append("wait")

            def close(self):
                events.append("close-link")

        class FakeSitl:
            def ensure_running(self, context="SITL"):
                events.append("ensure-running")

            def stop(self):
                events.append("stop-sitl")

        class FinishedSim:
            def is_finished(self):
                return True

        args = SimpleNamespace(
            mode="sitl",
            host="localhost",
            tcp_port=5555,
            project=".",
            source="physics",
            no_auto_start=False,
            sitl_exe=None,
            sitl_log=None,
            show_sitl_output=False,
            build=False,
            header_probe="CMD/HEADER\n",
            ready_token="",
            ready_probe="",
            target_apogee=None,
            no_plot=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            with (
                mock.patch.object(session, "configure_console_output"),
                mock.patch.object(session, "_build_native_if_requested"),
                mock.patch.object(session, "load_custom_sim_hooks", return_value=(None, None)),
                mock.patch.object(session, "_create_builtin_sim", return_value=FinishedSim()),
                mock.patch.object(session, "TCPLink", FakeTCPLink),
                mock.patch.object(session, "_start_sitl_if_needed", side_effect=lambda *a, **k: events.append("start-sitl") or FakeSitl()),
                mock.patch.object(session, "_handshake", return_value=({}, ["Time"])),
                mock.patch.object(session, "write_sim_log"),
                mock.patch.object(session, "plot_history"),
                mock.patch.object(session.time, "strftime", return_value="20260101_000000"),
            ):
                exit_code = session.run_simulation(args, project_root)

        self.assertEqual(exit_code, 0)
        self.assertEqual(events[:3], ["listen", "start-sitl", "wait"])

    def test_record_packet_extracts_velocity_and_acceleration_fields_with_normalized_units(self):
        expected_alt = 321.0
        packet = SimpleNamespace(
            timestamp=12.5,
            truth_alt=321.0,
            alt=320.5,
            pressure=data_sources.pressure_from_msl_altitude(expected_alt),
            truth_accel=18.2,
        )
        fields = {
            "State - VZ (m/s)": "87.4",
            "State - AZ (m/s\u00b2)": "-4.6",
            "State - Flight Stage": "BOOST",
        }

        record = session._record_packet(packet, fields, [])
        baseline = session._apply_pressure_altitude_baseline(record, math.nan)

        self.assertEqual(record["sim_alt"], 321.0)
        self.assertAlmostEqual(record["sensor_alt_agl_m"], 0.0, places=3)
        self.assertEqual(record["sim_acc_mps2"], 18.2)
        self.assertTrue(math.isnan(record["sensor_acc_z_mps2"]))
        self.assertEqual(record["fc_stage"], "BOOST")
        self.assertEqual(record["fc_vel_z_mps"], 87.4)
        self.assertEqual(record["fc_acc_z_mps2"], -4.6)
        self.assertAlmostEqual(baseline, expected_alt, places=3)

    def test_record_packet_captures_sensor_acceleration_z(self):
        packet = SimpleNamespace(
            timestamp=0.5,
            truth_alt=10.0,
            alt=10.0,
            pressure=data_sources.pressure_from_msl_altitude(10.0),
            truth_accel=5.0,
            accel=[0.2, -0.1, 12.34],
        )

        record = session._record_packet(packet, {}, [])

        self.assertEqual(record["sensor_acc_z_mps2"], 12.34)
