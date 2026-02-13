import argparse
import time
import sys
import datetime
import csv
import importlib.util
import inspect
import matplotlib.pyplot as plt
import subprocess
import os
import platform
from pathlib import Path

try:
    from . import astra_link
    from . import astra_sim
except ImportError:
    import astra_link  # type: ignore
    import astra_sim  # type: ignore

def configure_console_output() -> None:
    # Ensure UTF-8 output so Unicode UI glyphs render on Windows shells
    # that default to cp1252.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

# Terminal colors
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    GRAY = '\033[90m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_MAGENTA = '\033[95m'

# Flight stage names and colors for visualization
STAGE_NAMES = {
    0: ('PAD_IDLE', 'gray', Colors.GRAY),
    1: ('BOOST', 'red', Colors.FAIL),
    2: ('COAST', 'orange', Colors.WARNING),
    3: ('APOGEE', 'purple', Colors.BRIGHT_MAGENTA),
    4: ('EXPECTING_DROGUE', 'brown', Colors.WARNING),
    5: ('UNDER_DROGUE', 'blue', Colors.OKBLUE),
    6: ('EXPECTING_MAIN', 'cyan', Colors.BRIGHT_CYAN),
    7: ('UNDER_MAIN', 'green', Colors.OKGREEN),
    8: ('LANDED', 'black', Colors.GRAY)
}

def parse_telem_header(header_line):
    """Parses 'TELEM/Time,Alt,...' into a map and a list"""
    if not header_line.startswith("TELEM/"): return None, None
    raw = header_line[6:].strip()
    parts = [p.strip() for p in raw.split(',')]
    col_map = {name: i for i, name in enumerate(parts)}
    return col_map, parts


def _extract_fc_fields(current_values: list[str], fc_col_map) -> dict[str, str]:
    fields: dict[str, str] = {}
    if not fc_col_map:
        return fields
    for key, idx in fc_col_map.items():
        if idx < len(current_values):
            fields[key] = current_values[idx]
    return fields


def _support_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _source_alias_kind(source_text: str) -> str:
    token = source_text.strip().lower()
    if token in {"physics", "phys", "p"}:
        return "physics"
    if token in {"net", "network", "udp"}:
        return "net"
    if token in {"csv"}:
        return "csv"
    return "csv_path"


def _iter_csv_files(root: Path):
    if not root.exists():
        return
    for csv_path in root.rglob("*.csv"):
        if csv_path.is_file():
            yield csv_path


def _list_builtin_csv_files(project_root: Path) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()
    for base in (
        _support_repo_root() / "flight-data",
        project_root / "flight-data",
    ):
        for csv_path in _iter_csv_files(base):
            key = str(csv_path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(csv_path.resolve())
    candidates.sort(key=lambda p: str(p).lower())
    return candidates


def _resolve_csv_source(source_text: str, project_root: Path) -> Path:
    requested = source_text.strip().strip('"').strip("'")
    source_path = Path(requested)
    path_candidates: list[Path] = []
    if source_path.is_absolute():
        path_candidates.append(source_path)
    else:
        path_candidates.extend(
            [
                Path.cwd() / source_path,
                project_root / source_path,
                _support_repo_root() / source_path,
            ]
        )
        if source_path.suffix.lower() != ".csv":
            csv_guess = source_path.with_suffix(".csv")
            path_candidates.extend(
                [
                    Path.cwd() / csv_guess,
                    project_root / csv_guess,
                    _support_repo_root() / csv_guess,
                ]
            )

    resolved_seen: set[str] = set()
    for candidate in path_candidates:
        if candidate.is_file():
            resolved = candidate.resolve()
            key = str(resolved).lower()
            if key in resolved_seen:
                continue
            resolved_seen.add(key)
            return resolved

    builtin_files = _list_builtin_csv_files(project_root)
    requested_lower = source_path.name.lower()
    requested_stem_lower = source_path.stem.lower()
    matches: list[Path] = []
    for candidate in builtin_files:
        name_lower = candidate.name.lower()
        stem_lower = candidate.stem.lower()
        rel_lower = str(candidate).lower()
        if requested_lower == name_lower:
            matches.append(candidate)
            continue
        if requested_stem_lower and requested_stem_lower == stem_lower:
            matches.append(candidate)
            continue
        if requested_lower and requested_lower in rel_lower:
            matches.append(candidate)

    unique_matches: list[Path] = []
    seen_matches: set[str] = set()
    for match in matches:
        key = str(match.resolve()).lower()
        if key in seen_matches:
            continue
        seen_matches.add(key)
        unique_matches.append(match.resolve())

    if len(unique_matches) == 1:
        return unique_matches[0]
    if len(unique_matches) > 1:
        raise ValueError(
            "Source is ambiguous. Matches:\n  - "
            + "\n  - ".join(str(path) for path in unique_matches[:10])
            + ("\n  - ..." if len(unique_matches) > 10 else "")
        )

    available = [path.name for path in builtin_files]
    preview = ", ".join(sorted(available)[:12])
    raise ValueError(
        f"Could not resolve CSV source '{source_text}'. "
        f"Checked local/project paths and built-in flight-data. "
        f"Available built-in sims include: {preview}"
        + ("..." if len(available) > 12 else "")
    )


def _load_custom_sim_hooks(project_root: Path):
    module_path = project_root / "astra_support_sim.py"
    if not module_path.is_file():
        return None, None

    module_name = f"astra_support_custom_sim_{abs(hash(str(module_path.resolve())))}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    create_fn = getattr(module, "create_data_source", None)
    list_fn = getattr(module, "list_sim_sources", None)

    if create_fn is not None and not callable(create_fn):
        raise TypeError(f"{module_path}: create_data_source must be callable")
    if list_fn is not None and not callable(list_fn):
        raise TypeError(f"{module_path}: list_sim_sources must be callable")

    return create_fn, list_fn


def _invoke_hook(func, available_kwargs: dict[str, object], positional_fallback: list[object]):
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params):
        return func(**available_kwargs)

    keyword_candidates = [
        p.name
        for p in params
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    ]
    if keyword_candidates:
        kwargs = {name: available_kwargs[name] for name in keyword_candidates if name in available_kwargs}
        required = [
            p.name
            for p in params
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and p.default is inspect._empty
        ]
        if all(name in kwargs for name in required):
            return func(**kwargs)

    positional_count = len(
        [
            p
            for p in params
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
    )
    return func(*positional_fallback[:positional_count])

def main(argv=None):
    configure_console_output()

    parser = argparse.ArgumentParser(
        description="Astra Rocket Handshake Sim",
        epilog="""
Examples:
  # Basic SITL with internal physics
  python run_sim.py --mode sitl --source physics

  # SITL with a specific CSV path
  python run_sim.py --mode sitl --source flight-data/astra-rocket/raw/NyxORK.csv

  # SITL with a built-in sim name (no full path needed)
  python run_sim.py --mode sitl --source NyxORK

  # HITL with random rotation (simulates tilted rail)
  python run_sim.py --mode hitl --port COM3 --source data_160_trimmed --rotate

  # With specific rotation and noise
  python run_sim.py --mode sitl --source physics --rotation 0 10 45 --noise

  # Custom noise levels for realistic hardware simulation
  python run_sim.py --mode sitl --source NyxORK --noise --accel-noise 0.1 --baro-noise 1.0
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--mode', '-m', choices=['hitl', 'sitl'], required=True, help="Connection mode")
    parser.add_argument(
        '--source',
        '-s',
        default='physics',
        metavar='physics|net|<file.csv>',
        help=(
            "Simulation source. Use 'physics' or 'net', or pass a CSV name/path "
            "(e.g. NyxORK, data_160_trimmed.csv, or full path). "
            "Optional project custom source hook: <project>/astra_support_sim.py"
        ),
    )
    parser.add_argument('--port', '-p', help="Serial port (HITL)")
    parser.add_argument('--baud', '-b', type=int, default=115200, help="Baud rate")
    parser.add_argument('--host', '-H', default='localhost', help="TCP Host (SITL)")
    parser.add_argument('--tcp-port', '-t', type=int, default=5555, help="TCP Port (SITL)")
    parser.add_argument('--udp-port', '-u', type=int, default=9000, help="External UDP port")
    parser.add_argument(
        '--project',
        '-C',
        default='.',
        help="Path to target PlatformIO project root (default: current directory)"
    )

    # SITL executable options
    parser.add_argument('--sitl-exe', '-x', help="Path to SITL executable (default: .pio/build/native/program.exe)")
    parser.add_argument('--no-auto-start', '-N', action='store_true', help="Don't auto-start SITL executable (manual start required)")
    parser.add_argument('--show-sitl-output', '-v', action='store_true', help="Show child SITL process stdout/stderr inline")
    parser.add_argument('--sitl-log', '-L', help="Child SITL output log path (default: <project>/.pio_native_verbose.log)")
    parser.add_argument('--build', '-B', action='store_true', help="Build native environment with 'pio run -e native' before running")
    parser.add_argument('--list-sims', '-l', action='store_true', help="List discovered built-in CSV simulations and exit")

    # Sensor simulation options
    parser.add_argument('--rotate', '-r', action='store_true', help="Apply random rotation to sensor data (simulates tilted rail)")
    parser.add_argument('--rotation', '-R', type=float, nargs=3, metavar=('ROLL', 'PITCH', 'YAW'),
                       help="Apply specific rotation in degrees (e.g., --rotation 0 10 45)")
    parser.add_argument('--noise', '-n', action='store_true', help="Add Gaussian noise to sensor data")
    parser.add_argument('--accel-noise', '-a', type=float, default=0.05, help="Accelerometer noise std dev (m/s²), default=0.05")
    parser.add_argument('--gyro-noise', '-g', type=float, default=0.01, help="Gyroscope noise std dev (rad/s), default=0.01")
    parser.add_argument('--mag-noise', '-j', type=float, default=0.5, help="Magnetometer noise std dev (uT), default=0.5")
    parser.add_argument('--baro-noise', '-z', type=float, default=0.5, help="Barometer noise std dev (hPa), default=0.5")

    args = parser.parse_args(argv)
    project_root = Path(args.project).resolve()
    custom_create_fn = None
    custom_list_fn = None

    try:
        custom_create_fn, custom_list_fn = _load_custom_sim_hooks(project_root)
    except Exception as exc:
        parser.error(f"Failed to load custom simulator module: {exc}")

    if args.list_sims:
        sims = _list_builtin_csv_files(project_root)
        custom_sources = []
        if custom_list_fn:
            listed = _invoke_hook(
                custom_list_fn,
                {"project_root": project_root, "args": args},
                [project_root, args],
            )
            if listed:
                custom_sources = [str(item) for item in listed]

        if not sims and not custom_sources:
            print("No built-in or custom simulations found.")
            return 1

        if sims:
            print("Available built-in CSV simulations:")
            support_root = _support_repo_root()
            for sim_path in sims:
                try:
                    rel = sim_path.relative_to(support_root)
                    display = str(rel)
                except ValueError:
                    display = str(sim_path)
                print(f"  - {sim_path.stem:<20} ({display})")

        if custom_sources:
            print("Available custom simulations:")
            for source_name in custom_sources:
                print(f"  - {source_name}")
        return 0

    custom_sim = None
    if custom_create_fn:
        try:
            custom_sim = _invoke_hook(
                custom_create_fn,
                {
                    "source": args.source,
                    "project_root": project_root,
                    "astra_sim_module": astra_sim,
                    "args": args,
                },
                [args.source, project_root, astra_sim, args],
            )
        except Exception as exc:
            parser.error(f"Custom simulator error for source '{args.source}': {exc}")

    source_kind = _source_alias_kind(args.source)
    resolved_csv_file: Path | None = None
    try:
        if custom_sim is None and source_kind in {"csv", "csv_path"}:
            if source_kind == "csv":
                parser.error(
                    "CSV source now uses only --source <file.csv>. "
                    "Example: --source NyxORK or --source flight-data/astra-rocket/raw/NyxORK.csv"
                )
            resolved_csv_file = _resolve_csv_source(args.source, project_root)
    except ValueError as exc:
        parser.error(str(exc))

    auto_started_sitl = args.mode == 'sitl' and not args.no_auto_start
    connect_timeout_s = 20.0 if auto_started_sitl else None
    handshake_timeout_s = 20.0 if auto_started_sitl else None
    max_consecutive_fc_timeouts = 20 if auto_started_sitl else None

    # --- 0. Build Native Environment (if requested) ---
    if args.build:
        print(f"{Colors.OKCYAN}[Build]{Colors.ENDC} Building native environment...")
        print(f"{Colors.GRAY}[Build]{Colors.ENDC} Running: {Colors.BOLD}pio run -e native{Colors.ENDC}")

        try:
            result = subprocess.run(
                ['pio', 'run', '-e', 'native'],
                cwd=project_root,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print(f"{Colors.OKGREEN}[Build]{Colors.ENDC} Build successful!")
            else:
                print(f"{Colors.FAIL}[Build]{Colors.ENDC} Build failed with return code {result.returncode}")
                print(f"{Colors.FAIL}[Build]{Colors.ENDC} stderr: {result.stderr}")
                sys.exit(1)

        except FileNotFoundError:
            print(f"{Colors.FAIL}[Build]{Colors.ENDC} 'pio' command not found. Make sure PlatformIO is installed.")
            sys.exit(1)
        except Exception as e:
            print(f"{Colors.FAIL}[Build]{Colors.ENDC} Build error: {e}")
            sys.exit(1)

    # --- 1. Start SITL Executable (if needed) ---
    sitl_process = None
    sitl_log_handle = None

    def stop_sitl_process() -> None:
        nonlocal sitl_process
        nonlocal sitl_log_handle
        if sitl_process:
            print(f"{Colors.OKCYAN}[SITL]{Colors.ENDC} Terminating SITL process...")
            sitl_process.terminate()
            try:
                sitl_process.wait(timeout=5.0)
                print(f"{Colors.OKGREEN}[SITL]{Colors.ENDC} Process terminated gracefully")
            except subprocess.TimeoutExpired:
                print(f"{Colors.WARNING}[SITL]{Colors.ENDC} Process did not terminate, killing...")
                sitl_process.kill()
                sitl_process.wait()
            sitl_process = None

        if sitl_log_handle:
            sitl_log_handle.close()
            sitl_log_handle = None

    if auto_started_sitl:
        # Determine SITL executable path
        if args.sitl_exe:
            sitl_exe_path = args.sitl_exe
        else:
            # Determine executable name based on platform
            if platform.system() == 'Windows':
                exe_name = 'program.exe'
            else:  # Linux, macOS, etc.
                exe_name = 'program'

            sitl_exe_path = os.path.join(project_root, '.pio', 'build', 'native', exe_name)

        # Check if executable exists
        if os.path.exists(sitl_exe_path):
            print(f"{Colors.OKCYAN}[SITL]{Colors.ENDC} Starting executable: {Colors.BOLD}{sitl_exe_path}{Colors.ENDC}")
            try:
                popen_kwargs = {"cwd": project_root}
                if args.show_sitl_output:
                    print(f"{Colors.GRAY}[SITL]{Colors.ENDC} Child process output: {Colors.BOLD}inline{Colors.ENDC}")
                else:
                    sitl_log_path = Path(args.sitl_log).resolve() if args.sitl_log else project_root / ".pio_native_verbose.log"
                    sitl_log_handle = open(sitl_log_path, "a", encoding="utf-8")
                    popen_kwargs["stdout"] = sitl_log_handle
                    popen_kwargs["stderr"] = subprocess.STDOUT
                    print(f"{Colors.GRAY}[SITL]{Colors.ENDC} Child process output: {Colors.BOLD}{sitl_log_path}{Colors.ENDC}")

                sitl_process = subprocess.Popen(
                    [sitl_exe_path],
                    **popen_kwargs
                )
                print(f"{Colors.OKGREEN}[SITL]{Colors.ENDC} Process started (PID: {Colors.BOLD}{sitl_process.pid}{Colors.ENDC})")
            except Exception as e:
                if sitl_log_handle:
                    sitl_log_handle.close()
                    sitl_log_handle = None
                print(f"{Colors.WARNING}[SITL]{Colors.ENDC} Warning: Could not start executable: {e}")
                print(f"{Colors.WARNING}[SITL]{Colors.ENDC} Please start the SITL executable manually")
        else:
            print(f"{Colors.FAIL}[SITL]{Colors.ENDC} Executable not found at: {sitl_exe_path}")
            print(f"{Colors.WARNING}[SITL]{Colors.ENDC} Please build the project or specify --sitl-exe")
            print(f"{Colors.WARNING}[SITL]{Colors.ENDC} Or use --no-auto-start to start SITL manually")

    # --- 2. Setup Link ---
    try:
        if args.mode == 'hitl':
            if not args.port: raise ValueError("--port required for HITL")
            print(f"{Colors.OKCYAN}[Link]{Colors.ENDC} Connecting to HITL on {Colors.BOLD}{args.port}{Colors.ENDC} @ {args.baud} baud...")
            link = astra_link.SerialLink(args.port, args.baud)
            print(f"{Colors.OKGREEN}[Link]{Colors.ENDC} Connected!")
        else:
            print(f"{Colors.OKCYAN}[Link]{Colors.ENDC} Connecting to SITL on {Colors.BOLD}{args.host}:{args.tcp_port}{Colors.ENDC}...")
            link = astra_link.TCPLink(args.host, args.tcp_port, connect_timeout_s=connect_timeout_s)
            print(f"{Colors.OKGREEN}[Link]{Colors.ENDC} Connected!")
    except Exception as e:
        print(f"{Colors.FAIL}Connection Failed: {e}{Colors.ENDC}")
        stop_sitl_process()
        sys.exit(1)

    # --- 3. Setup Source ---
    try:
        if custom_sim is not None:
            print(f"{Colors.OKCYAN}[Sim]{Colors.ENDC} Using custom simulator source: {Colors.BOLD}{args.source}{Colors.ENDC}")
            base_sim = custom_sim
        elif source_kind == 'net':
            print(f"{Colors.OKCYAN}[Sim]{Colors.ENDC} Starting Network Stream on port {Colors.BOLD}{args.udp_port}{Colors.ENDC}")
            base_sim = astra_sim.NetworkStreamSim(args.udp_port)
        elif source_kind == 'physics':
            print(f"{Colors.OKCYAN}[Sim]{Colors.ENDC} Starting Physics Simulation")
            base_sim = astra_sim.PhysicsSim()
        else:
            if resolved_csv_file is None:
                raise ValueError("CSV source could not be resolved.")
            print(f"{Colors.OKCYAN}[Sim]{Colors.ENDC} Loading CSV file: {Colors.BOLD}{resolved_csv_file}{Colors.ENDC}")
            base_sim = astra_sim.CSVSim(str(resolved_csv_file))

        # Apply pad delay only for OpenRocket or PhysicsSim (not for real flight data)
        # Real flight data already starts at the right time
        if isinstance(base_sim, astra_sim.CSVSim) and base_sim.is_openrocket:
            sim = astra_sim.PadDelaySim(base_sim)
        elif isinstance(base_sim, astra_sim.PhysicsSim):
            sim = astra_sim.PadDelaySim(base_sim)
        else:
            sim = base_sim

        # Apply rotation wrapper if requested
        if args.rotate:
            print(f"{Colors.BRIGHT_CYAN}[Sim]{Colors.ENDC} Applying random rotation")
            sim = astra_sim.RotatedSim(sim)
        elif args.rotation:
            print(f"{Colors.BRIGHT_CYAN}[Sim]{Colors.ENDC} Applying rotation: {args.rotation}")
            sim = astra_sim.RotatedSim(sim, rotation_deg=args.rotation)

        # Apply noise wrapper if requested
        if args.noise:
            print(f"{Colors.BRIGHT_CYAN}[Sim]{Colors.ENDC} Adding sensor noise (accel={args.accel_noise}, gyro={args.gyro_noise}, mag={args.mag_noise}, baro={args.baro_noise})")
            sim = astra_sim.NoisySim(sim,
                                     accel_noise=args.accel_noise,
                                     gyro_noise=args.gyro_noise,
                                     mag_noise=args.mag_noise,
                                     baro_noise=args.baro_noise)

        print(f"{Colors.OKGREEN}[Sim]{Colors.ENDC} Simulation source ready!")

    except Exception as e:
        print(f"{Colors.FAIL}Sim Setup Failed: {e}{Colors.ENDC}")
        link.close()
        stop_sitl_process()
        sys.exit(1)

    # --- 4. Handshake Phase ---
    print(f"\n{Colors.OKCYAN}[Init]{Colors.ENDC} Waiting for Flight Computer Header...")
    if not sitl_process:
        print(f"       {Colors.GRAY}(Please reset/boot the Flight Computer now){Colors.ENDC}")

    fc_col_map = None
    fc_header_names = []
    handshake_deadline = None
    if handshake_timeout_s is not None:
        handshake_deadline = time.monotonic() + handshake_timeout_s

    # Wait for the header (with Ctrl+C support)
    try:
        while True:
            if sitl_process and sitl_process.poll() is not None:
                raise ConnectionError(f"SITL process exited during handshake (code {sitl_process.returncode})")
            if handshake_deadline is not None and time.monotonic() >= handshake_deadline:
                raise TimeoutError(
                    f"Timed out waiting for TELEM header after {handshake_timeout_s:.1f}s from auto-started SITL process"
                )
            line = link.read_line()
            if line and line.startswith("TELEM/") and ("State" in line or "Time" in line):
                fc_col_map, fc_header_names = parse_telem_header(line)
                if fc_header_names:
                    print(f"{Colors.OKGREEN}[Init]{Colors.ENDC} Header Received! Found {Colors.BOLD}{len(fc_header_names)}{Colors.ENDC} columns.")
                    print(f"{Colors.GRAY}[Init]{Colors.ENDC} Columns: {fc_header_names}")
                break
            time.sleep(0.01)  # Small sleep allows Ctrl+C to be detected
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}[Init]{Colors.ENDC} Interrupted by user during handshake.")
        link.close()
        stop_sitl_process()
        sys.exit(0)
    except TimeoutError as e:
        print(f"\n{Colors.FAIL}[Error]{Colors.ENDC} Handshake timeout: {e}")
        link.close()
        stop_sitl_process()
        sys.exit(1)
    except ConnectionError as e:
        print(f"\n{Colors.FAIL}[Error]{Colors.ENDC} Connection died during handshake: {e}")
        link.close()
        stop_sitl_process()
        sys.exit(1)

    print(f"{Colors.OKGREEN}[Init]{Colors.ENDC} Handshake Complete. Starting Simulation in 1s...")
    time.sleep(1.0)

    # --- 5. Main Loop ---
    print(f"\n{Colors.BOLD}{Colors.HEADER}╔═══════════════════════════════════════════════════════════════╗{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}║          Starting LOCK-STEP Simulation                        ║{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}╚═══════════════════════════════════════════════════════════════╝{Colors.ENDC}\n")
    print(f"{Colors.BOLD}{Colors.OKCYAN}{'Time (s)':<9} | {'SimAlt':<8} | {'FC Alt':<8} | {'Events':<30}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKCYAN}{'-'*9}-+-{'-'*8}-+-{'-'*8}-+-{'-'*30}{Colors.ENDC}")

    history = {
        'time': [],
        'sim_alt': [],           # Ground truth altitude
        'sensor_alt': [],        # Altitude from pressure sensor (with noise if enabled)
        'fc_alt': [],            # KF estimate from flight computer
        'fc_stage': [],
        'fc_flap_cmd_deg': [],   # FC desired flap angle from AirbrakeController
        'fc_flap_actual_deg': [],# FC measured/actual flap angle
        'fc_est_apogee_m': [],   # FC estimated/predicted apogee
        'fc_target_apogee_m': [],# FC desired/target apogee setpoint
        'fc_mach': [],           # FC-estimated Mach number
        'fc_transonic_lockout': [], # FC transonic lockout active flag (0/1)
        'fc_values': [],
        'truth_accel': [],       # Ground truth acceleration (from sim)
        'sensor_accel': [],      # Measured acceleration (from accel sensor)
        'fc_accel': [],          # KF estimated acceleration
        'csv_accel_vec': [],     # Raw accelerometer from CSV (before any transforms)
        'hitl_accel_vec': [],    # HITL accelerometer 3-axis vector sent to FC
        'fc_hitl_accel_vec': [], # FC's echo of HITL accelerometer (from FC response)
        'fc_accel_vec': [],      # FC state 3-axis acceleration vector
        'fc_vel_vec': []         # FC state 3-axis velocity vector
    }
    last_stage = "BOOT"
    pkt_count = 0
    
    connection_alive = True
    run_failed = False
    consecutive_fc_timeouts = 0
    sim_hook_warned = False
    if custom_sim is not None:
        sim_source_name = f"CUSTOM ({args.source})"
    elif source_kind == "physics":
        sim_source_name = "PHYSICS"
    elif source_kind == "net":
        sim_source_name = "NET"
    elif resolved_csv_file:
        sim_source_name = f"CSV ({resolved_csv_file.name})"
    else:
        sim_source_name = args.source.upper()

    try:
        while connection_alive:
            if sitl_process and sitl_process.poll() is not None:
                print(
                    f"\n{Colors.FAIL}[SITL]{Colors.ENDC} Auto-started SITL process exited unexpectedly "
                    f"(code {sitl_process.returncode})."
                )
                run_failed = True
                break

            # A. Get Next Packet
            if sim.is_finished():
                print(f"\n{Colors.OKGREEN}[Sim]{Colors.ENDC} Source finished. Exiting loop.")
                break

            packet = sim.get_next_packet()
            pkt_count += 1
            msg = packet.to_hitl_string().encode()

            # B. Send & Wait (Retry Logic)
            attempts = 0
            max_retries = 3
            fc_response_line = None

            while attempts < max_retries:
                try:
                    link.send(msg)
                except ConnectionError as e:
                    print(f"\n{Colors.FAIL}[Link] Connection Died during send: {e}{Colors.ENDC}")
                    connection_alive = False
                    run_failed = True
                    break

                # Wait for Response (1.0s timeout)
                start_wait = time.time()
                got_response = False

                while (time.time() - start_wait) < 1.0:
                    try:
                        line = link.read_line()
                        if line and line.startswith("TELEM/"):
                            fc_response_line = line
                            got_response = True
                            break
                    except ConnectionError as e:
                        print(f"\n{Colors.FAIL}[Link] Connection Died during read: {e}{Colors.ENDC}")
                        connection_alive = False
                        run_failed = True
                        break

                if not connection_alive:
                    break

                if got_response:
                    consecutive_fc_timeouts = 0
                    break
                else:
                    attempts += 1

            if not connection_alive:
                break

            if attempts >= max_retries:
                consecutive_fc_timeouts += 1
                if pkt_count % 50 == 0:
                     print(f"\r{Colors.WARNING}[FC] Timeout - Packet {pkt_count} skipped.{Colors.ENDC}\033[K", end='')
                if (
                    max_consecutive_fc_timeouts is not None
                    and consecutive_fc_timeouts >= max_consecutive_fc_timeouts
                ):
                    print(
                        f"\n{Colors.FAIL}[FC]{Colors.ENDC} No TELEM responses for "
                        f"{consecutive_fc_timeouts} consecutive packets from auto-started SITL process."
                    )
                    run_failed = True
                    connection_alive = False
                    break
                continue # Skip this step

            # C. Parse Response
            fc_alt_val = 0.0
            fc_accel_val = 0.0
            fc_stage_val = last_stage
            fc_flap_cmd_deg = float("nan")
            fc_flap_actual_deg = float("nan")
            fc_est_apogee_m = float("nan")
            fc_target_apogee_m = float("nan")
            fc_mach = float("nan")
            fc_transonic_lockout = float("nan")
            current_values = []
            fc_accel_x, fc_accel_y, fc_accel_z = 0.0, 0.0, 0.0
            fc_vel_x, fc_vel_y, fc_vel_z = 0.0, 0.0, 0.0
            fc_hitl_acc_x, fc_hitl_acc_y, fc_hitl_acc_z = 0.0, 0.0, 0.0

            if fc_response_line:
                raw_content = fc_response_line[6:].strip()
                current_values = [x.strip() for x in raw_content.split(',')]

                # Optional simulator feedback hook: allows custom simulators to
                # ingest FC telemetry (e.g., commanded flap angle) for the next
                # simulation step.
                if hasattr(sim, "on_fc_telemetry"):
                    try:
                        fc_fields = _extract_fc_fields(current_values, fc_col_map)
                        sim.on_fc_telemetry(fc_fields)
                    except Exception as hook_error:
                        if not sim_hook_warned:
                            print(
                                f"\n{Colors.WARNING}[Sim]{Colors.ENDC} "
                                f"custom telemetry hook error: {hook_error}"
                            )
                            sim_hook_warned = True

                if fc_col_map:
                    def get_fc(keys_list, default):
                        for k in keys_list:
                            if k in fc_col_map and fc_col_map[k] < len(current_values):
                                return current_values[fc_col_map[k]]
                        return default

                    fc_alt_str = get_fc(["State - PZ (m)", "Alt", "State - Alt (m)"], "0")
                    fc_accel_str = get_fc(["State - AZ (m/s/s)", "State - AZ (m/s^2)", "State - AZ (m/s²)", "Accel Z", "AZ", "State - AZ"], "0")
                    fc_accel_x_str = get_fc(["State - AX (m/s/s)", "State - AX (m/s^2)", "State - AX"], "0")
                    fc_accel_y_str = get_fc(["State - AY (m/s/s)", "State - AY (m/s^2)", "State - AY"], "0")
                    fc_vel_x_str = get_fc(["State - VX (m/s)", "State - VX"], "0")
                    fc_vel_y_str = get_fc(["State - VY (m/s)", "State - VY"], "0")
                    fc_vel_z_str = get_fc(["State - VZ (m/s)", "State - VZ"], "0")
                    # Get HITL accelerometer values from FC response
                    fc_hitl_acc_x_str = get_fc(["HITL_Accelerometer - Acc X (m/s^2)", "HITL Acc X"], "0")
                    fc_hitl_acc_y_str = get_fc(["HITL_Accelerometer - Acc Y (m/s^2)", "HITL Acc Y"], "0")
                    fc_hitl_acc_z_str = get_fc(["HITL_Accelerometer - Acc Z (m/s^2)", "HITL Acc Z"], "0")
                    temp_stage = get_fc(["State - Flight Stage", "Stage"], last_stage)
                    fc_flap_cmd_str = get_fc(
                        [
                            "AirbrakeCtrl - Actuation Angle (deg)",
                            "State - Actuation Angle (deg)",
                            "Actuation Angle (deg)",
                        ],
                        "",
                    )
                    fc_flap_actual_str = get_fc(
                        [
                            "AirbrakeCtrl - Actual Angle (deg)",
                            "State - Actual Angle (deg)",
                            "State - Acutal Angle (deg)",
                            "Actual Angle (deg)",
                            "Acutal Angle (deg)",
                        ],
                        "",
                    )
                    fc_est_apogee_str = get_fc(
                        [
                            "AirbrakeCtrl - Pred Apogee (m)",
                            "State - Est Apo (m)",
                            "Pred Apogee (m)",
                            "Est Apo (m)",
                        ],
                        "",
                    )
                    fc_target_apogee_str = get_fc(
                        [
                            "AirbrakeCtrl - Target Apogee (m)",
                            "State - Target Apogee (m)",
                            "Target Apogee (m)",
                        ],
                        "",
                    )
                    fc_mach_str = get_fc(
                        [
                            "AirbrakeCtrl - Mach",
                            "State - Mach",
                            "Mach",
                        ],
                        "",
                    )
                    fc_transonic_lockout_str = get_fc(
                        [
                            "AirbrakeCtrl - Transonic Lockout",
                            "State - Transonic Lockout",
                            "Transonic Lockout",
                        ],
                        "",
                    )
                    if "-" in temp_stage: temp_stage = temp_stage.split('-')[-1].strip()
                    fc_stage_val = temp_stage
                    try: fc_alt_val = float(fc_alt_str)
                    except: pass
                    try: fc_accel_val = float(fc_accel_str)
                    except: pass

                    # Parse acceleration and velocity vectors
                    fc_accel_z = fc_accel_val
                    try: fc_accel_x = float(fc_accel_x_str)
                    except: pass
                    try: fc_accel_y = float(fc_accel_y_str)
                    except: pass
                    try: fc_vel_x = float(fc_vel_x_str)
                    except: pass
                    try: fc_vel_y = float(fc_vel_y_str)
                    except: pass
                    try: fc_vel_z = float(fc_vel_z_str)
                    except: pass
                    # Parse HITL accelerometer echo from FC
                    try: fc_hitl_acc_x = float(fc_hitl_acc_x_str)
                    except: pass
                    try: fc_hitl_acc_y = float(fc_hitl_acc_y_str)
                    except: pass
                    try: fc_hitl_acc_z = float(fc_hitl_acc_z_str)
                    except: pass
                    try: fc_flap_cmd_deg = float(fc_flap_cmd_str)
                    except: pass
                    try: fc_flap_actual_deg = float(fc_flap_actual_str)
                    except: pass
                    try: fc_est_apogee_m = float(fc_est_apogee_str)
                    except: pass
                    try: fc_target_apogee_m = float(fc_target_apogee_str)
                    except: pass
                    try: fc_mach = float(fc_mach_str)
                    except: pass
                    try: fc_transonic_lockout = float(fc_transonic_lockout_str)
                    except: pass

            # D. Store & Display
            history['time'].append(packet.timestamp)
            history['sim_alt'].append(packet.truth_alt if packet.truth_alt is not None else packet.alt)  # Ground truth
            history['sensor_alt'].append(packet.alt)     # Altitude from sensors (with noise if enabled)
            history['fc_alt'].append(fc_alt_val)
            history['fc_stage'].append(fc_stage_val)
            history['fc_flap_cmd_deg'].append(fc_flap_cmd_deg)
            history['fc_flap_actual_deg'].append(fc_flap_actual_deg)
            history['fc_est_apogee_m'].append(fc_est_apogee_m)
            history['fc_target_apogee_m'].append(fc_target_apogee_m)
            history['fc_mach'].append(fc_mach)
            history['fc_transonic_lockout'].append(fc_transonic_lockout)
            history['fc_values'].append(current_values)
            history['truth_accel'].append(packet.truth_accel if packet.truth_accel is not None else 0.0)  # Ground truth inertial accel
            history['sensor_accel'].append(packet.accel[2])  # Sensor measured specific force (z-axis)
            history['fc_accel'].append(fc_accel_val)  # KF estimated acceleration
            history['csv_accel_vec'].append([packet.accel[0], packet.accel[1], packet.accel[2]])  # Raw CSV accel (same as HITL)
            history['hitl_accel_vec'].append([packet.accel[0], packet.accel[1], packet.accel[2]])  # HITL 3-axis accel sent to FC
            history['fc_hitl_accel_vec'].append([fc_hitl_acc_x, fc_hitl_acc_y, fc_hitl_acc_z])  # FC's echo of HITL accel
            history['fc_accel_vec'].append([fc_accel_x, fc_accel_y, fc_accel_z])  # FC state 3-axis accel
            history['fc_vel_vec'].append([fc_vel_x, fc_vel_y, fc_vel_z])  # FC state 3-axis velocity

            is_event = (fc_stage_val != last_stage)

            # Get stage info for display
            stage_display = ""
            stage_color = Colors.ENDC
            try:
                stage_num = int(fc_stage_val)
                if stage_num in STAGE_NAMES:
                    stage_name, _, stage_color = STAGE_NAMES[stage_num]
                    stage_display = stage_name
                else:
                    stage_display = str(stage_num)
            except:
                stage_display = str(fc_stage_val)

            # Format the row with better spacing
            time_str = f"{packet.timestamp:>8.2f}"
            sim_alt_display = packet.truth_alt if packet.truth_alt is not None else packet.alt
            sim_alt_str = f"{sim_alt_display:>8.1f}"
            fc_alt_str = f"{fc_alt_val:>8.1f}"

            if is_event:
                event_str = f"{stage_color}STAGE: {stage_display}{Colors.ENDC}"
                print(f"\r{Colors.BRIGHT_YELLOW}{time_str}{Colors.ENDC} | {Colors.OKCYAN}{sim_alt_str}{Colors.ENDC} | {Colors.WARNING}{fc_alt_str}{Colors.ENDC} | {event_str}\033[K")
            elif pkt_count % 50 == 0:
                sys.stdout.write(f"\r{Colors.GRAY}{time_str} | {sim_alt_str} | {fc_alt_str} | {stage_color}{stage_display}{Colors.ENDC}\033[K")
                sys.stdout.flush()

            last_stage = fc_stage_val

    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Stopping...{Colors.ENDC}")
    finally:
        link.close()

        # Terminate SITL process if we started it
        stop_sitl_process()

        print(f"\n{Colors.BOLD}{Colors.OKGREEN}Simulation Closed.{Colors.ENDC}")
        
       # --- Save CSV Log ---
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_name = f"sim_log_{timestamp_str}.csv"
        print(f"{Colors.OKCYAN}Saving log to {Colors.BOLD}{log_name}{Colors.ENDC}{Colors.OKCYAN}...{Colors.ENDC}")
        
        try:
            with open(log_name, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Header
                csv_header = ['Sim_Time', 'Sim_Alt']
                if fc_header_names: csv_header.extend(fc_header_names)
                else: csv_header.append("FC_Raw_Data")
                writer.writerow(csv_header)

                # Rows
                for i in range(len(history['time'])):
                    row = [history['time'][i], history['sim_alt'][i]]
                    fc_row_data = history['fc_values'][i]
                    
                    if fc_header_names:
                        if len(fc_row_data) >= len(fc_header_names):
                            row.extend(fc_row_data[:len(fc_header_names)])
                        else:
                            row.extend(fc_row_data + [''] * (len(fc_header_names) - len(fc_row_data)))
                    else:
                        row.extend(fc_row_data)
                    writer.writerow(row)
        except Exception as e:
            print(f"{Colors.FAIL}Error saving log: {e}{Colors.ENDC}")

        # --- Plot ---
        print(f"{Colors.OKCYAN}Plotting results...{Colors.ENDC}")
        try:
            # Single airbrake graph:
            # - left axis: apogee/altitude (drives y-gridlines)
            # - right axis: desired/actual flap angle
            fig, ax_apo = plt.subplots(1, 1, figsize=(12, 8))
            ax_ab = ax_apo.twinx()

            ax_apo.plot(
                history['time'],
                history['fc_est_apogee_m'],
                label='Estimated Apogee (m)',
                color='tab:red',
                linewidth=1.8,
                alpha=0.9,
            )
            target_apogee_values = [
                v for v in history['fc_target_apogee_m']
                if isinstance(v, (int, float)) and v == v
            ]
            clean_fc_alt = [x for x in history['fc_alt'] if isinstance(x, (int, float)) and x == x]
            actual_apogee_m = max(clean_fc_alt) if clean_fc_alt else None
            clean_fc_est = [x for x in history['fc_est_apogee_m'] if isinstance(x, (int, float)) and x == x]
            predicted_apogee_m = clean_fc_est[-1] if clean_fc_est else None
            if target_apogee_values:
                target_apogee_m = target_apogee_values[-1]
                ax_apo.axhline(
                    y=target_apogee_m,
                    label=f'Desired Apogee ({target_apogee_m:.0f} m)',
                    color='tab:purple',
                    linewidth=1.6,
                    linestyle='-.',
                    alpha=0.85,
                )
                if actual_apogee_m is not None:
                    ax_apo.axhline(
                        y=actual_apogee_m,
                        label=f'Actual Apogee ({actual_apogee_m:.0f} m)',
                        color='tab:gray',
                        linewidth=1.4,
                        linestyle='--',
                        alpha=0.9,
                    )
                    apogee_error_m = target_apogee_m - actual_apogee_m
                    # Legend-only label for quick target-vs-actual error readout.
                    ax_apo.plot(
                        [],
                        [],
                        linestyle='none',
                        label=f'Apogee Error (Target-Actual): {apogee_error_m:+.1f} m',
                    )
            if predicted_apogee_m is not None and actual_apogee_m is not None:
                pred_error_m = predicted_apogee_m - actual_apogee_m
                ax_apo.plot(
                    [],
                    [],
                    linestyle='none',
                    label=f'Apogee Error (Pred-Actual): {pred_error_m:+.1f} m',
                )

            # Keep FC altitude for context on same right axis.
            clean_fc_alt = [x if x != 0 else None for x in history['fc_alt']]
            ax_apo.plot(
                history['time'],
                clean_fc_alt,
                label='FC Altitude (m)',
                color='orange',
                linewidth=1.3,
                linestyle=':',
                alpha=0.55,
            )
            ax_apo.set_ylabel("Apogee / Altitude (m)", fontsize=10)
            ax_apo.grid(True, which='both', linestyle='--', alpha=0.35)

            ax_ab.plot(
                history['time'],
                history['fc_flap_cmd_deg'],
                label='Desired Flap Angle (deg)',
                color='tab:blue',
                linewidth=2,
            )
            ax_ab.plot(
                history['time'],
                history['fc_flap_actual_deg'],
                label='Actual Flap Angle (deg)',
                color='tab:green',
                linewidth=2,
                linestyle='--',
            )
            ax_ab.set_ylabel("Flap Angle (deg)", fontsize=10)

            # Stage transitions
            labeled_stages = set()
            y_min, y_max = ax_apo.get_ylim()
            sim_alt_max = max(history['sim_alt']) if history['sim_alt'] else y_max
            if sim_alt_max > 0 and y_max < sim_alt_max:
                y_max = sim_alt_max * 1.1
                ax_apo.set_ylim(top=y_max)

            for i in range(1, len(history['fc_stage'])):
                if history['fc_stage'][i] != history['fc_stage'][i-1]:
                    event_time = history['time'][i]
                    stage_val = history['fc_stage'][i]
                    try:
                        stage_num = int(stage_val)
                        stage_name, stage_color, _ = STAGE_NAMES.get(stage_num, (str(stage_num), 'blue', Colors.OKBLUE))
                    except:
                        stage_name = str(stage_val)
                        stage_color = 'blue'

                    label = f"Stage: {stage_name}"
                    if label in labeled_stages:
                        label = None
                    else:
                        labeled_stages.add(label)

                    ax_apo.axvline(
                        x=event_time,
                        color=stage_color,
                        linestyle='-',
                        linewidth=1.2,
                        alpha=0.75,
                        label=label,
                    )
                    ax_apo.text(
                        event_time,
                        y_max * 0.95 if y_max > 0 else 0.0,
                        f" {stage_name}",
                        color=stage_color,
                        rotation=90,
                        verticalalignment='top',
                        fontweight='bold',
                        fontsize=8,
                    )

            # Lockout release marker (first transition from active->inactive)
            lockout_vals = history.get('fc_transonic_lockout', [])
            lockout_release_t = None
            for i in range(1, len(lockout_vals)):
                prev = lockout_vals[i - 1]
                curr = lockout_vals[i]
                if not (isinstance(prev, (int, float)) and prev == prev):
                    continue
                if not (isinstance(curr, (int, float)) and curr == curr):
                    continue
                if prev > 0.5 and curr <= 0.5:
                    lockout_release_t = history['time'][i]
                    break
            if lockout_release_t is not None:
                ax_apo.axvline(
                    x=lockout_release_t,
                    color='tab:olive',
                    linestyle='--',
                    linewidth=1.5,
                    alpha=0.9,
                    label='Lockout Released',
                )
                ax_apo.text(
                    lockout_release_t,
                    y_max * 0.88 if y_max > 0 else 0.0,
                    " Lockout Off",
                    color='tab:olive',
                    rotation=90,
                    verticalalignment='top',
                    fontweight='bold',
                    fontsize=8,
                )

            ax_apo.set_title("Airbrake Controller Telemetry", fontsize=12, fontweight='bold')

            ab_handles, ab_labels = ax_ab.get_legend_handles_labels()
            apo_handles, apo_labels = ax_apo.get_legend_handles_labels()
            ax_apo.legend(ab_handles + apo_handles, ab_labels + apo_labels, loc='best', fontsize=9, framealpha=0.9)

            ax_apo.set_xlabel("Time (s)", fontsize=10)

            # Overall figure title
            fig.suptitle(f"Flight Data Analysis - Source: {sim_source_name}",
                        fontsize=16, fontweight='bold', y=0.995)

            plt.tight_layout()
            plt.show()

        except Exception as e:
            print(f"{Colors.FAIL}Plotting error: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()

    return 1 if run_failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
