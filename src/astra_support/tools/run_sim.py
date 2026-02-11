import argparse
import time
import sys
import datetime
import csv
import matplotlib.pyplot as plt
import subprocess
import os
import platform
try:
    from . import astra_link
    from . import astra_sim
except ImportError:
    import astra_link  # type: ignore
    import astra_sim  # type: ignore

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

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Astra Rocket Handshake Sim",
        epilog="""
Examples:
  # Basic SITL with CSV data (auto-starts SITL executable)
  python run_sim.py --mode sitl --source csv --file flight.csv

  # SITL with custom executable path
  python run_sim.py --mode sitl --source csv --file flight.csv --sitl-exe path/to/program.exe

  # SITL without auto-start (start SITL executable manually)
  python run_sim.py --mode sitl --source physics --no-auto-start

  # HITL with random rotation (simulates tilted rail)
  python run_sim.py --mode hitl --port COM3 --source csv --file flight.csv --rotate

  # With specific rotation and noise
  python run_sim.py --mode sitl --source physics --rotation 0 10 45 --noise

  # Custom noise levels for realistic hardware simulation
  python run_sim.py --mode sitl --source csv --file flight.csv --noise --accel-noise 0.1 --baro-noise 1.0
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--mode', choices=['hitl', 'sitl'], required=True, help="Connection mode")
    parser.add_argument('--source', choices=['physics', 'csv', 'net'], default='physics', help="Data source")
    parser.add_argument('--port', help="Serial port (HITL)")
    parser.add_argument('--baud', type=int, default=115200, help="Baud rate")
    parser.add_argument('--host', default='localhost', help="TCP Host (SITL)")
    parser.add_argument('--tcp-port', type=int, default=5555, help="TCP Port (SITL)")
    parser.add_argument('--file', help="CSV file path")
    parser.add_argument('--udp-port', type=int, default=9000, help="External UDP port")
    parser.add_argument(
        '--project',
        default='.',
        help="Path to target PlatformIO project root (default: current directory)"
    )

    # SITL executable options
    parser.add_argument('--sitl-exe', help="Path to SITL executable (default: .pio/build/native/program.exe)")
    parser.add_argument('--no-auto-start', action='store_true', help="Don't auto-start SITL executable (manual start required)")
    parser.add_argument('--build', action='store_true', help="Build native environment with 'pio run -e native' before running")

    # Sensor simulation options
    parser.add_argument('--rotate', action='store_true', help="Apply random rotation to sensor data (simulates tilted rail)")
    parser.add_argument('--rotation', type=float, nargs=3, metavar=('ROLL', 'PITCH', 'YAW'),
                       help="Apply specific rotation in degrees (e.g., --rotation 0 10 45)")
    parser.add_argument('--noise', action='store_true', help="Add Gaussian noise to sensor data")
    parser.add_argument('--accel-noise', type=float, default=0.05, help="Accelerometer noise std dev (m/s²), default=0.05")
    parser.add_argument('--gyro-noise', type=float, default=0.01, help="Gyroscope noise std dev (rad/s), default=0.01")
    parser.add_argument('--mag-noise', type=float, default=0.5, help="Magnetometer noise std dev (uT), default=0.5")
    parser.add_argument('--baro-noise', type=float, default=0.5, help="Barometer noise std dev (hPa), default=0.5")

    args = parser.parse_args(argv)
    project_root = os.path.abspath(args.project)

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
    if args.mode == 'sitl' and not args.no_auto_start:
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
                sitl_process = subprocess.Popen(
                    [sitl_exe_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0
                )
                print(f"{Colors.OKGREEN}[SITL]{Colors.ENDC} Process started (PID: {Colors.BOLD}{sitl_process.pid}{Colors.ENDC})")
                # Give it a moment to start up
                time.sleep(1.0)
            except Exception as e:
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
            link = astra_link.TCPLink(args.host, args.tcp_port)
            print(f"{Colors.OKGREEN}[Link]{Colors.ENDC} Connected!")
    except Exception as e:
        print(f"{Colors.FAIL}Connection Failed: {e}{Colors.ENDC}")
        if sitl_process:
            print(f"{Colors.OKCYAN}[SITL]{Colors.ENDC} Terminating SITL process...")
            sitl_process.terminate()
            sitl_process.wait()
        sys.exit(1)

    # --- 3. Setup Source ---
    try:
        if args.source == 'csv':
            if not args.file: raise ValueError("--file required for CSV mode")
            print(f"{Colors.OKCYAN}[Sim]{Colors.ENDC} Loading CSV file: {Colors.BOLD}{args.file}{Colors.ENDC}")
            base_sim = astra_sim.CSVSim(args.file)
        elif args.source == 'net':
            print(f"{Colors.OKCYAN}[Sim]{Colors.ENDC} Starting Network Stream on port {Colors.BOLD}{args.udp_port}{Colors.ENDC}")
            base_sim = astra_sim.NetworkStreamSim(args.udp_port)
        else:
            print(f"{Colors.OKCYAN}[Sim]{Colors.ENDC} Starting Physics Simulation")
            base_sim = astra_sim.PhysicsSim()

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
        if sitl_process:
            print(f"{Colors.OKCYAN}[SITL]{Colors.ENDC} Terminating SITL process...")
            sitl_process.terminate()
            sitl_process.wait()
        sys.exit(1)

    # --- 4. Handshake Phase ---
    print(f"\n{Colors.OKCYAN}[Init]{Colors.ENDC} Waiting for Flight Computer Header...")
    if not sitl_process:
        print(f"       {Colors.GRAY}(Please reset/boot the Flight Computer now){Colors.ENDC}")

    fc_col_map = None
    fc_header_names = []

    # Wait for the header (with Ctrl+C support)
    try:
        while True:
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
        if sitl_process:
            print(f"{Colors.OKCYAN}[SITL]{Colors.ENDC} Terminating SITL process...")
            sitl_process.terminate()
            sitl_process.wait()
        sys.exit(0)
    except ConnectionError as e:
        print(f"\n{Colors.FAIL}[Error]{Colors.ENDC} Connection died during handshake: {e}")
        link.close()
        if sitl_process:
            print(f"{Colors.OKCYAN}[SITL]{Colors.ENDC} Terminating SITL process...")
            sitl_process.terminate()
            sitl_process.wait()
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
    sim_source_name = args.source.upper()
    if args.source == 'csv' and args.file:
        sim_source_name = f"CSV ({os.path.basename(args.file)})"

    try:
        while connection_alive:
            # A. Get Next Packet
            if sim.is_finished():
                print(f"\n{Colors.OKGREEN}[Sim]{Colors.ENDC} CSV Finished. Exiting Loop.")
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
                        break

                if not connection_alive:
                    break

                if got_response:
                    break
                else:
                    attempts += 1

            if not connection_alive:
                break

            if attempts >= max_retries:
                if pkt_count % 50 == 0:
                     print(f"\r{Colors.WARNING}[FC] Timeout - Packet {pkt_count} skipped.{Colors.ENDC}\033[K", end='')
                continue # Skip this step

            # C. Parse Response
            fc_alt_val = 0.0
            fc_accel_val = 0.0
            fc_stage_val = last_stage
            current_values = []
            fc_accel_x, fc_accel_y, fc_accel_z = 0.0, 0.0, 0.0
            fc_vel_x, fc_vel_y, fc_vel_z = 0.0, 0.0, 0.0
            fc_hitl_acc_x, fc_hitl_acc_y, fc_hitl_acc_z = 0.0, 0.0, 0.0

            if fc_response_line:
                raw_content = fc_response_line[6:].strip()
                current_values = [x.strip() for x in raw_content.split(',')]

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

            # D. Store & Display
            history['time'].append(packet.timestamp)
            history['sim_alt'].append(packet.truth_alt if packet.truth_alt is not None else packet.alt)  # Ground truth
            history['sensor_alt'].append(packet.alt)     # Altitude from sensors (with noise if enabled)
            history['fc_alt'].append(fc_alt_val)
            history['fc_stage'].append(fc_stage_val)
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
            sim_alt_str = f"{packet.alt:>8.1f}"
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
            # Create single altitude plot
            fig, ax_alt = plt.subplots(1, 1, figsize=(12, 8))

            # ===== ALTITUDE PLOT =====
            ax_alt.plot(history['time'], history['sim_alt'],
                        label='Ground Truth', color='black', linewidth=2.5, alpha=0.6)
            ax_alt.plot(history['time'], history['sensor_alt'],
                        label='Raw Sensor Data', color='gray', linewidth=1, alpha=0.4)
            clean_fc = [x if x != 0 else None for x in history['fc_alt']]
            ax_alt.plot(history['time'], clean_fc,
                        label='FC Estimate (KF)', color='orange', linewidth=2, linestyle='--')

            # ===== STAGE TRANSITIONS (on altitude plot) =====
            labeled_stages = set()
            y_min, y_max = ax_alt.get_ylim()
            if y_max < max(history['sim_alt']): y_max = max(history['sim_alt']) * 1.1

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

                    ax_alt.axvline(x=event_time, color=stage_color, linestyle='-',
                                  linewidth=1.5, alpha=0.8, label=label)
                    ax_alt.text(event_time, y_max * 0.95, f" {stage_name}",
                               color=stage_color, rotation=90,
                               verticalalignment='top', fontweight='bold', fontsize=9)

            # Add unlabeled vertical lines at specific times
            ax_alt.axvline(x=7.056, color='black', linestyle='--', linewidth=1, alpha=0.5)
            ax_alt.axvline(x=9.238, color='black', linestyle='--', linewidth=1, alpha=0.5)

            # Styling for altitude plot
            ax_alt.set_title(f"Altitude & State Estimation", fontsize=12, fontweight='bold')
            ax_alt.set_xlabel("Time (s)", fontsize=10)
            ax_alt.set_ylabel("Altitude (m)", fontsize=10)
            ax_alt.grid(True, which='both', linestyle='--', alpha=0.4)
            ax_alt.legend(loc='best', fontsize=9, framealpha=0.9)
            ax_alt.set_ylim(top=y_max)

            # Overall figure title
            fig.suptitle(f"Flight Data Analysis - Source: {sim_source_name}",
                        fontsize=16, fontweight='bold', y=0.995)

            plt.tight_layout()
            plt.show()

        except Exception as e:
            print(f"{Colors.FAIL}Plotting error: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    raise SystemExit(main())
