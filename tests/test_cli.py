from __future__ import annotations

import argparse
import unittest
from unittest import mock

from astra_support import cli


class CliTests(unittest.TestCase):
    def test_doctor_command_parses(self):
        parser = cli.build_parser()
        args = parser.parse_args(["doctor", "--project", "."])
        self.assertEqual(args.command, "doctor")
        self.assertEqual(args.project, ".")

    def test_sim_run_command_parses(self):
        parser = cli.build_parser()
        args = parser.parse_args(["sim", "run", "--mode", "sitl", "--source", "physics"])
        self.assertEqual(args.command, "sim")
        self.assertEqual(args.sim_command, "run")
        self.assertEqual(args.mode, "sitl")
        self.assertEqual(args.source, "physics")

    def test_compat_sitl_does_not_mutate_namespace(self):
        args = argparse.Namespace(
            project=".",
            config=None,
            source="physics",
            sitl_exe=None,
            build=False,
            no_auto_start=False,
            show_sitl_output=False,
            sitl_log=None,
            host="localhost",
            tcp_port=5555,
            udp_port=9000,
            rotate=False,
            rotation=None,
            noise=False,
            accel_noise=0.05,
            gyro_noise=0.01,
            mag_noise=0.5,
            baro_noise=0.5,
            header_probe="CMD/HEADER\n",
            target_apogee=None,
            dataset_root=None,
            no_plot=True,
        )
        with mock.patch.object(cli.sim_cmd, "run", return_value=0) as patched:
            cli._compat_sitl(args)
        self.assertFalse(hasattr(args, "mode"))
        forwarded = patched.call_args.args[0]
        self.assertEqual(forwarded.mode, "sitl")

    def test_compat_hitl_does_not_mutate_namespace(self):
        args = argparse.Namespace(
            project=".",
            config=None,
            source="physics",
            port="COM3",
            baud=115200,
            udp_port=9000,
            rotate=False,
            rotation=None,
            noise=False,
            accel_noise=0.05,
            gyro_noise=0.01,
            mag_noise=0.5,
            baro_noise=0.5,
            ready_token="HITL READY",
            ready_probe="HITL/READY?\n",
            header_probe="CMD/HEADER\n",
            target_apogee=None,
            real_time=False,
            time_scale=1.0,
            dataset_root=None,
            no_plot=True,
        )
        with mock.patch.object(cli.sim_cmd, "run", return_value=0) as patched:
            cli._compat_hitl(args)
        self.assertFalse(hasattr(args, "mode"))
        forwarded = patched.call_args.args[0]
        self.assertEqual(forwarded.mode, "hitl")

    def test_main_handles_keyboard_interrupt_cleanly(self):
        with (
            mock.patch.object(cli, "maybe_prompt_for_update", return_value=False),
            mock.patch.object(cli.doctor_cmd, "run", side_effect=KeyboardInterrupt),
            mock.patch("builtins.print") as patched_print,
        ):
            exit_code = cli.main(["doctor", "--project", "."])

        self.assertEqual(exit_code, 130)
        self.assertIn("Interrupted by user.", patched_print.call_args.args[0])
