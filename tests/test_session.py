from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from astra_support.sim import session


class SessionTests(unittest.TestCase):
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
