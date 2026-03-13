from __future__ import annotations

import argparse
from types import SimpleNamespace

from . import __version__
from .commands import doctor as doctor_cmd
from .commands import sim as sim_cmd
from .commands import sync as sync_cmd
from .commands import test as test_cmd
from .self_update import maybe_prompt_for_update


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="astra-support", description="Astra support CLI")
    parser.add_argument("--version", action="version", version=f"astra-support {__version__}")
    parser.add_argument(
        "--no-update-check",
        "-U",
        action="store_true",
        help="Skip interactive CLI update checks for this invocation.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="Validate project, toolchain, and Astra Support readiness")
    p_doctor.add_argument("--project", "-C", default=".", help="Target project path")
    p_doctor.add_argument("--config", help="Optional path to .astra-support.yml")
    p_doctor.set_defaults(func=doctor_cmd.run)

    p_sync = sub.add_parser("sync", help="Write or refresh support-managed project files")
    p_sync.add_argument("--project", "-C", default=".", help="Target project path")
    p_sync.add_argument("--config", help="Optional path to .astra-support.yml")
    p_sync.add_argument("--write-workflow", action="store_true", help="Write a GitHub workflow for Astra Support")
    p_sync.add_argument("--overwrite", action="store_true", help="Overwrite existing generated files")
    p_sync.add_argument("--skip-platformio-env", action="store_true", help="Do not append managed env snippets")
    p_sync.add_argument("--env", action="append", help="Managed env to sync; repeatable")
    p_sync.add_argument("--list-envs", action="store_true", help="Print supported env keys and exit")
    p_sync.add_argument(
        "--support-install",
        default="git+https://github.com/Terrapin-Rocket-Team/Astra-Support.git@main",
        help="pip/pipx install spec written into generated workflow",
    )
    p_sync.set_defaults(func=sync_cmd.run)

    p_test = sub.add_parser("test", help="Run managed PlatformIO clean/build/test flows")
    p_test.add_argument("--project", "-C", default=".", help="Target project path")
    p_test.add_argument("--config", help="Optional path to .astra-support.yml")
    p_test.add_argument("--env", action="append", help="Limit work to specific env(s)")
    p_test.add_argument("--no-progress", "-P", action="store_true")
    p_test.add_argument("--no-install", "-I", action="store_true")
    p_test.add_argument("--no-builds", "-B", action="store_true")
    p_test.add_argument("--no-tests", "-T", action="store_true")
    p_test.add_argument("--clean", "-c", action="store_true")
    p_test.set_defaults(func=test_cmd.run)

    p_sim = sub.add_parser("sim", help="Simulation utilities")
    p_sim_sub = p_sim.add_subparsers(dest="sim_command", required=True)

    p_sim_list = p_sim_sub.add_parser("list", help="List available bundled, local, and custom sim sources")
    p_sim_list.add_argument("--project", "-C", default=".", help="Target project path")
    p_sim_list.add_argument("--config", help="Optional path to .astra-support.yml")
    p_sim_list.set_defaults(func=sim_cmd.list_sources)

    p_sim_run = p_sim_sub.add_parser("run", help="Run the simulation harness")
    p_sim_run.add_argument("--project", "-C", default=".", help="Target project path")
    p_sim_run.add_argument("--config", help="Optional path to .astra-support.yml")
    p_sim_run.add_argument("--mode", "-m", choices=["hitl", "sitl"], required=True, help="Simulation mode")
    p_sim_run.add_argument("--source", "-s", default="physics", help="Simulation source name or CSV path")
    p_sim_run.add_argument("--port", "-p", help="Serial port for HITL")
    p_sim_run.add_argument("--baud", "-b", type=int, default=115200, help="Serial baud rate")
    p_sim_run.add_argument("--host", "-H", default="localhost", help="TCP host for SITL")
    p_sim_run.add_argument("--tcp-port", "-t", type=int, default=5555, help="TCP port for SITL")
    p_sim_run.add_argument("--udp-port", "-u", type=int, default=9000, help="UDP source port for net mode")
    p_sim_run.add_argument("--sitl-exe", "-x", help="Path to the SITL executable")
    p_sim_run.add_argument("--no-auto-start", "-N", action="store_true", help="Do not auto-start the SITL executable")
    p_sim_run.add_argument("--show-sitl-output", "-v", action="store_true", help="Echo SITL stdout/stderr inline")
    p_sim_run.add_argument("--sitl-log", "-L", help="Path for captured SITL output")
    p_sim_run.add_argument("--build", "-B", action="store_true", help="Build the native environment before running SITL")
    p_sim_run.add_argument("--rotate", "-r", action="store_true", help="Apply a random 90-degree rotation")
    p_sim_run.add_argument("--rotation", "-R", type=float, nargs=3, metavar=("ROLL", "PITCH", "YAW"))
    p_sim_run.add_argument("--noise", "-n", action="store_true", help="Add Gaussian noise to sensor data")
    p_sim_run.add_argument("--accel-noise", "-a", type=float, default=0.05)
    p_sim_run.add_argument("--gyro-noise", "-g", type=float, default=0.01)
    p_sim_run.add_argument("--mag-noise", "-j", type=float, default=0.5)
    p_sim_run.add_argument("--baro-noise", "-z", type=float, default=0.5)
    p_sim_run.add_argument("--ready-token", default="HITL READY")
    p_sim_run.add_argument("--ready-probe", default="HITL/READY?\n")
    p_sim_run.add_argument("--header-probe", default="CMD/HEADER\n")
    p_sim_run.add_argument("--target-apogee", type=float, default=None)
    p_sim_run.add_argument("--real-time", action="store_true", help="Pace HITL packets to sim timestamps")
    p_sim_run.add_argument("--time-scale", type=float, default=1.0, help="Real-time pacing scale factor")
    p_sim_run.add_argument("--dataset-root", action="append", help="Additional dataset roots")
    p_sim_run.add_argument("--no-plot", action="store_true", help="Skip result plotting")
    p_sim_run.set_defaults(func=sim_cmd.run)

    p_init = sub.add_parser("init", help="Compatibility alias for sync")
    p_init.add_argument("--project", "-C", default=".", help="Target project path")
    p_init.add_argument("--config", help="Optional path to .astra-support.yml")
    p_init.add_argument("--write-workflow", action="store_true", help="Write a GitHub workflow for Astra Support")
    p_init.add_argument("--overwrite", action="store_true", help="Overwrite existing generated files")
    p_init.add_argument("--skip-platformio-env", action="store_true", help="Do not append managed env snippets")
    p_init.add_argument("--env", action="append", help="Managed env to sync; repeatable")
    p_init.add_argument("--list-envs", action="store_true", help="Print supported env keys and exit")
    p_init.add_argument(
        "--support-install",
        default="git+https://github.com/Terrapin-Rocket-Team/Astra-Support.git@main",
        help="pip/pipx install spec written into generated workflow",
    )
    p_init.set_defaults(func=sync_cmd.run)

    p_sitl = sub.add_parser("sitl", help="Compatibility alias for 'sim run --mode sitl'")
    p_sitl.add_argument("--project", "-C", default=".", help="Target project path")
    p_sitl.add_argument("--config", help="Optional path to .astra-support.yml")
    p_sitl.add_argument("--source", "-s", default="physics")
    p_sitl.add_argument("--sitl-exe", "-x")
    p_sitl.add_argument("--build", "-B", action="store_true")
    p_sitl.add_argument("--no-auto-start", "-N", action="store_true")
    p_sitl.add_argument("--show-sitl-output", "-v", action="store_true")
    p_sitl.add_argument("--sitl-log", "-L")
    p_sitl.add_argument("--host", "-H", default="localhost")
    p_sitl.add_argument("--tcp-port", "-t", type=int, default=5555)
    p_sitl.add_argument("--udp-port", "-u", type=int, default=9000)
    p_sitl.add_argument("--rotate", "-r", action="store_true")
    p_sitl.add_argument("--rotation", "-R", type=float, nargs=3)
    p_sitl.add_argument("--noise", "-n", action="store_true")
    p_sitl.add_argument("--accel-noise", "-a", type=float, default=0.05)
    p_sitl.add_argument("--gyro-noise", "-g", type=float, default=0.01)
    p_sitl.add_argument("--mag-noise", "-j", type=float, default=0.5)
    p_sitl.add_argument("--baro-noise", "-z", type=float, default=0.5)
    p_sitl.add_argument("--header-probe", default="CMD/HEADER\n")
    p_sitl.add_argument("--target-apogee", type=float, default=None)
    p_sitl.add_argument("--dataset-root", action="append")
    p_sitl.add_argument("--no-plot", action="store_true")
    p_sitl.set_defaults(func=_compat_sitl)

    p_hitl = sub.add_parser("hitl", help="Compatibility alias for 'sim run --mode hitl'")
    p_hitl.add_argument("--project", "-C", default=".", help="Target project path")
    p_hitl.add_argument("--config", help="Optional path to .astra-support.yml")
    p_hitl.add_argument("--source", "-s", default="physics")
    p_hitl.add_argument("--port", "-p")
    p_hitl.add_argument("--baud", "-b", type=int, default=115200)
    p_hitl.add_argument("--udp-port", "-u", type=int, default=9000)
    p_hitl.add_argument("--rotate", "-r", action="store_true")
    p_hitl.add_argument("--rotation", "-R", type=float, nargs=3)
    p_hitl.add_argument("--noise", "-n", action="store_true")
    p_hitl.add_argument("--accel-noise", "-a", type=float, default=0.05)
    p_hitl.add_argument("--gyro-noise", "-g", type=float, default=0.01)
    p_hitl.add_argument("--mag-noise", "-j", type=float, default=0.5)
    p_hitl.add_argument("--baro-noise", "-z", type=float, default=0.5)
    p_hitl.add_argument("--ready-token", default="HITL READY")
    p_hitl.add_argument("--ready-probe", default="HITL/READY?\n")
    p_hitl.add_argument("--header-probe", default="CMD/HEADER\n")
    p_hitl.add_argument("--target-apogee", type=float, default=None)
    p_hitl.add_argument("--real-time", action="store_true")
    p_hitl.add_argument("--time-scale", type=float, default=1.0)
    p_hitl.add_argument("--dataset-root", action="append")
    p_hitl.add_argument("--no-plot", action="store_true")
    p_hitl.set_defaults(func=_compat_hitl)

    return parser


def _compat_sitl(args) -> int:
    compat_args = SimpleNamespace(
        **vars(args),
        mode="sitl",
        ready_token="",
        ready_probe="",
        port=None,
        baud=115200,
        real_time=False,
        time_scale=1.0,
    )
    return sim_cmd.run(compat_args)


def _compat_hitl(args) -> int:
    compat_args = SimpleNamespace(
        **vars(args),
        mode="hitl",
        host="localhost",
        tcp_port=5555,
        sitl_exe=None,
        no_auto_start=True,
        show_sitl_output=False,
        sitl_log=None,
        build=False,
    )
    return sim_cmd.run(compat_args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if maybe_prompt_for_update(no_update_check=args.no_update_check):
        return 0
    return int(args.func(args))
