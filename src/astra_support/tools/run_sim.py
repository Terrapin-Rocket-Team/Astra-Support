from __future__ import annotations

from pathlib import Path

from ..sim.session import run_simulation


def main(argv=None):
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Compatibility wrapper for the Astra Support sim runner.")
    parser.add_argument("--project", "-C", default=".")
    parser.add_argument("--mode", "-m", choices=["hitl", "sitl"], required=True)
    parser.add_argument("--source", "-s", default="physics")
    parser.add_argument("--port", "-p")
    parser.add_argument("--baud", "-b", type=int, default=115200)
    parser.add_argument("--host", "-H", default="localhost")
    parser.add_argument("--tcp-port", "-t", type=int, default=5555)
    parser.add_argument("--udp-port", "-u", type=int, default=9000)
    parser.add_argument("--sitl-exe", "-x")
    parser.add_argument("--no-auto-start", "-N", action="store_true")
    parser.add_argument("--show-sitl-output", "-v", action="store_true")
    parser.add_argument("--sitl-log", "-L")
    parser.add_argument("--build", "-B", action="store_true")
    parser.add_argument("--rotate", "-r", action="store_true")
    parser.add_argument("--rotation", "-R", type=float, nargs=3)
    parser.add_argument("--noise", "-n", action="store_true")
    parser.add_argument("--accel-noise", "-a", type=float, default=0.05)
    parser.add_argument("--gyro-noise", "-g", type=float, default=0.01)
    parser.add_argument("--mag-noise", "-j", type=float, default=0.5)
    parser.add_argument("--baro-noise", "-z", type=float, default=0.5)
    parser.add_argument("--ready-token", default="HITL READY")
    parser.add_argument("--ready-probe", default="HITL/READY?\n")
    parser.add_argument("--header-probe", default="CMD/HEADER\n")
    parser.add_argument("--target-apogee", type=float, default=None)
    parser.add_argument("--real-time", action="store_true")
    parser.add_argument("--time-scale", type=float, default=1.0)
    parser.add_argument("--dataset-root", action="append")
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args(argv)
    return run_simulation(args, Path(args.project).resolve())
