from __future__ import annotations

import math
import subprocess
import time
from pathlib import Path

from ..console import Ansi, configure_console_output, paint
from ..prereqs import check_toolchain
from . import data_sources
from .logging import write_sim_log
from .plotting import plot_history
from .sitl_process import SitlProcess, default_sitl_executable
from .sources import invoke_hook, load_custom_sim_hooks, resolve_csv_source, source_kind
from .telemetry import extract_fc_fields, parse_telem_header
from .transport import SerialLink, TCPLink


def run_simulation(args, project_root: Path) -> int:
    configure_console_output()
    project_root = project_root.resolve()
    _build_native_if_requested(args, project_root)
    custom_create_fn, _ = load_custom_sim_hooks(project_root)
    custom_sim = _create_custom_sim(args, project_root, custom_create_fn)
    sim = custom_sim or _create_builtin_sim(args, project_root)

    sitl = None
    link = None
    fc_header_names: list[str] = []
    fc_col_map = None
    history = _new_history()
    run_failed = False

    try:
        if args.mode == "sitl":
            sitl = _start_sitl_if_needed(args, project_root)
            link = TCPLink(host=args.host, port=args.tcp_port, connect_timeout_s=20.0 if sitl else None)
        else:
            if not args.port:
                raise ValueError("--port is required in hitl mode")
            link = SerialLink(args.port, args.baud)

        fc_col_map, fc_header_names = _handshake(link, args, sitl=sitl)
        if args.target_apogee is not None:
            _send_preflight_airbrake_target(link, args.target_apogee)

        last_stage = "unknown"
        start_wall = time.time()
        first_timestamp = None
        while not sim.is_finished():
            if sitl is not None:
                sitl.ensure_running("SITL")
            packet = sim.get_next_packet()
            if first_timestamp is None:
                first_timestamp = packet.timestamp
            _pace_packet(args, packet.timestamp, first_timestamp, start_wall)
            link.send(packet.to_hitl_string().encode("utf-8"))
            response = _read_telem_response(link)
            current_values = response[6:].split(",") if response and response.startswith("TELEM/") else []
            fields = extract_fc_fields(current_values, fc_col_map)

            if hasattr(custom_sim, "on_fc_telemetry"):
                custom_sim.on_fc_telemetry(fields)

            record = _record_packet(packet, fields, current_values)
            for key, value in record.items():
                history[key].append(value)

            stage_value = record["fc_stage"]
            if stage_value != last_stage:
                print(
                    f"{paint(f'{packet.timestamp:8.2f}s', Ansi.YELLOW)} "
                    f"stage -> {paint(str(stage_value), Ansi.CYAN)}"
                )
                last_stage = stage_value
            elif len(history["time"]) % 50 == 0:
                sim_alt_text = f"{record['sim_alt']:8.1f}"
                fc_alt_text = _format_optional(record["fc_alt"])
                print(
                    f"{paint(f'{packet.timestamp:8.2f}s', Ansi.DIM)} "
                    f"sim_alt={paint(sim_alt_text, Ansi.CYAN)} "
                    f"fc_alt={paint(fc_alt_text, Ansi.YELLOW)} "
                    f"stage={paint(str(stage_value), Ansi.GRAY)}"
                )
    except Exception as exc:
        print(paint(f"Simulation failed: {exc}", Ansi.RED))
        run_failed = True
    except KeyboardInterrupt:
        print(paint("Simulation interrupted.", Ansi.YELLOW))
        run_failed = True
    finally:
        if link is not None:
            link.close()
        if sitl is not None:
            sitl.stop()

    log_path = Path(f"sim_log_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    write_sim_log(log_path, history, fc_header_names)
    print(paint(f"Saved log to {log_path}", Ansi.GREEN))
    if not getattr(args, "no_plot", False):
        plot_history(history, source_name=args.source)
    return 1 if run_failed else 0


def _build_native_if_requested(args, project_root: Path) -> None:
    if not args.build:
        return
    toolchain = check_toolchain(require_platformio=True, require_cpp=True, offer_install=True)
    if toolchain.errors:
        raise RuntimeError("\n".join(toolchain.errors))
    subprocess.run([*(toolchain.platformio_cmd or ["pio"]), "run", "-e", "native"], cwd=project_root, check=True)


def _create_custom_sim(args, project_root: Path, custom_create_fn):
    if custom_create_fn is None:
        return None
    return invoke_hook(
        custom_create_fn,
        {
            "source": args.source,
            "project_root": project_root,
            "astra_sim_module": data_sources,
            "args": args,
        },
        [args.source, project_root, data_sources, args],
    )


def _create_builtin_sim(args, project_root: Path):
    kind = source_kind(args.source)
    if kind == "net":
        base = data_sources.NetworkStreamSim(args.udp_port)
    elif kind == "physics":
        base = data_sources.PhysicsSim()
    else:
        csv_path = resolve_csv_source(args.source, project_root, extra_roots=getattr(args, "dataset_root", None))
        base = data_sources.CSVSim(str(csv_path))

    if isinstance(base, data_sources.CSVSim) and getattr(base, "is_openrocket", False):
        sim = data_sources.PadDelaySim(base)
    elif isinstance(base, data_sources.PhysicsSim):
        sim = data_sources.PadDelaySim(base)
    else:
        sim = base

    if args.rotate:
        sim = data_sources.RotatedSim(sim)
    elif args.rotation:
        sim = data_sources.RotatedSim(sim, rotation_deg=args.rotation)
    if args.noise:
        sim = data_sources.NoisySim(
            sim,
            accel_noise=args.accel_noise,
            gyro_noise=args.gyro_noise,
            mag_noise=args.mag_noise,
            baro_noise=args.baro_noise,
        )
    return sim


def _start_sitl_if_needed(args, project_root: Path) -> SitlProcess | None:
    if args.no_auto_start:
        return None
    executable = args.sitl_exe or str(default_sitl_executable(project_root))
    sitl = SitlProcess(
        project_root,
        executable,
        log_path=Path(args.sitl_log) if args.sitl_log else project_root / ".pio_native_verbose.log",
        echo_output=args.show_sitl_output,
    )
    sitl.start()
    return sitl


def _handshake(link, args, *, sitl: SitlProcess | None):
    fc_col_map = None
    fc_header_names: list[str] = []
    ready_token = args.ready_token.strip()
    require_ready = args.mode == "hitl" and bool(ready_token)
    ready_seen = False
    next_header_probe_at = time.monotonic()
    next_ready_probe_at = time.monotonic()
    deadline = time.monotonic() + 20.0

    while time.monotonic() < deadline:
        if sitl is not None:
            sitl.ensure_running("SITL")
        now = time.monotonic()
        if not fc_header_names and args.header_probe and now >= next_header_probe_at:
            link.send(args.header_probe.encode("utf-8"))
            next_header_probe_at = now + 0.5
        if require_ready and not ready_seen and args.ready_probe and now >= next_ready_probe_at:
            link.send(args.ready_probe.encode("utf-8"))
            next_ready_probe_at = now + 0.5

        line = link.read_line()
        if not line:
            time.sleep(0.01)
            continue
        if require_ready and ready_token in line:
            ready_seen = True
        if line.startswith("TELEM/") and ("State" in line or "Time" in line):
            fc_col_map, fc_header_names = parse_telem_header(line)
        if fc_header_names and (ready_seen or not require_ready):
            return fc_col_map, fc_header_names

    raise TimeoutError("Timed out waiting for FC handshake.")


def _send_preflight_airbrake_target(link, target_apogee_m: float) -> None:
    link.send(f"AB/TARGET_APOGEE {target_apogee_m:.2f}\n".encode("utf-8"))
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        line = link.read_line()
        if line and line.startswith("AB OK"):
            return
        time.sleep(0.01)


def _pace_packet(args, timestamp: float, first_timestamp: float, start_wall: float) -> None:
    if not (args.real_time and args.mode == "hitl"):
        return
    elapsed_sim = max(0.0, timestamp - first_timestamp)
    target = elapsed_sim / max(args.time_scale, 0.001)
    remaining = target - (time.time() - start_wall)
    if remaining > 0:
        time.sleep(remaining)


def _read_telem_response(link) -> str:
    deadline = time.time() + 1.0
    while time.time() < deadline:
        line = link.read_line()
        if line and line.startswith("TELEM/"):
            return line
        time.sleep(0.01)
    return ""


def _record_packet(packet, fields: dict[str, str], current_values: list[str]) -> dict[str, object]:
    fc_alt = _coerce_float(_pick(fields, ["State - PZ (m)", "State - Alt (m)", "Alt (m)"]))
    fc_stage = _pick(fields, ["State - Flight Stage", "Stage"], "unknown")
    fc_flap_cmd = _coerce_float(_pick(fields, ["AirbrakeCtrl - Actuation Angle (deg)", "Actuation Angle (deg)"]))
    fc_flap_actual = _coerce_float(_pick(fields, ["AirbrakeCtrl - Actual Angle (deg)", "Actual Angle (deg)"]))
    fc_est_apogee = _coerce_float(_pick(fields, ["AirbrakeCtrl - Pred Apogee (m)", "Pred Apogee (m)", "Est Apo (m)"]))
    fc_target_apogee = _coerce_float(_pick(fields, ["AirbrakeCtrl - Target Apogee (m)", "Target Apogee (m)"]))
    fc_mach = _coerce_float(_pick(fields, ["AirbrakeCtrl - Mach", "Mach"]))
    return {
        "time": packet.timestamp,
        "sim_alt": packet.truth_alt if packet.truth_alt is not None else packet.alt,
        "sensor_alt": packet.alt,
        "fc_alt": fc_alt,
        "fc_stage": fc_stage,
        "fc_flap_cmd_deg": fc_flap_cmd,
        "fc_flap_actual_deg": fc_flap_actual,
        "fc_est_apogee_m": fc_est_apogee,
        "fc_target_apogee_m": fc_target_apogee,
        "fc_mach": fc_mach,
        "fc_values": current_values,
    }


def _new_history() -> dict[str, list]:
    return {
        "time": [],
        "sim_alt": [],
        "sensor_alt": [],
        "fc_alt": [],
        "fc_stage": [],
        "fc_flap_cmd_deg": [],
        "fc_flap_actual_deg": [],
        "fc_est_apogee_m": [],
        "fc_target_apogee_m": [],
        "fc_mach": [],
        "fc_values": [],
    }


def _pick(fields: dict[str, str], names: list[str], default: str = "") -> str:
    for name in names:
        value = fields.get(name)
        if value not in (None, ""):
            return value
    return default


def _coerce_float(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return math.nan


def _format_optional(value: float) -> str:
    return f"{value:8.1f}" if not math.isnan(value) else "     n/a"
