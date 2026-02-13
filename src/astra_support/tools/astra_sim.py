import csv
import socket
import numpy as np
from dataclasses import dataclass
from scipy.spatial.transform import Rotation

@dataclass
class PacketData:
    timestamp: float
    accel: np.ndarray  # [x, y, z] m/s^2
    gyro: np.ndarray   # [x, y, z] rad/s
    mag: np.ndarray    # [x, y, z] uT
    pressure: float    # hPa
    temp: float        # C
    lat: float
    lon: float
    alt: float         # Altitude sent to FC (may have noise)
    fix: int
    sats: int
    heading: float
    truth_alt: float = None  # Ground truth altitude (before noise)
    truth_accel: float = None  # Ground truth inertial acceleration (before sensor transform)

    def to_hitl_string(self) -> str:
        return (f"HITL/{self.timestamp:.3f},"
                f"{self.accel[0]:.4f},{self.accel[1]:.4f},{self.accel[2]:.4f},"
                f"{self.gyro[0]:.4f},{self.gyro[1]:.4f},{self.gyro[2]:.4f},"
                f"{self.mag[0]:.2f},{self.mag[1]:.2f},{self.mag[2]:.2f},"
                f"{self.pressure:.2f},{self.temp:.2f},"
                f"{self.lat:.7f},{self.lon:.7f},{self.alt:.2f},"
                f"{self.fix},{self.sats},{self.heading:.1f}\n")

class DataSource:
    def get_next_packet(self) -> PacketData: raise NotImplementedError
    def is_finished(self) -> bool: return False

class PhysicsSim(DataSource):
    def __init__(self):
        self.t = 0.0
        self.alt = 0.0
        self.vel = 0.0
        self.dt = 0.02
        self.ignition_time = 2.0  # Motor ignites at t=2s
        self.motor_burnout_time = self.ignition_time + 2.0  # 2 second burn
        self.landed = False
        self.landed_time = None
        print("[Sim] Using Internal Physics Engine")

    def is_finished(self) -> bool:
        # Stop simulation 2 seconds after landing
        if self.landed and self.landed_time is not None:
            return (self.t - self.landed_time) > 2.0
        return False

    def get_next_packet(self) -> PacketData:
        self.t += self.dt

        # Before ignition: on pad
        if self.t < self.ignition_time:
            accel_z = 0.0
            self.alt = 0.0
            self.vel = 0.0
        # Motor burn
        elif self.t < self.motor_burnout_time:
            accel_z = 30.0
        # After burnout: free fall or on ground
        else:
            if self.alt > 0:
                accel_z = -9.81
            else:
                accel_z = 0.0
                self.vel = 0.0
                self.alt = 0.0
                if not self.landed:
                    self.landed = True
                    self.landed_time = self.t

        # Update dynamics
        self.vel += accel_z * self.dt
        self.alt += self.vel * self.dt

        # Ground constraint
        if self.alt < 0:
            self.alt = 0.0
            self.vel = 0.0
            if not self.landed:
                self.landed = True
                self.landed_time = self.t

        # Accelerometer measures specific force (not inertial acceleration)
        accel_measured = -accel_z - 9.81

        return PacketData(self.t, np.array([0., 0., accel_measured]), np.zeros(3), np.zeros(3),
                          1013.25 - (self.alt * 0.12), 25.0, 45.0, -122.0, self.alt, 1, 8, 0.0,
                          truth_alt=self.alt, truth_accel=accel_z)

class CSVSim(DataSource):
    def __init__(self, filename):
        self.data = []
        self.index = 0
        self.is_openrocket = False
        self._load_csv(filename)
        print(f"[Sim] Ready. Duration: {self.data[-1].timestamp:.1f}s")

    def is_finished(self) -> bool:
        return self.index >= len(self.data)

    def get_next_packet(self) -> PacketData:
        if self.index < len(self.data):
            p = self.data[self.index]
            self.index += 1
            return p
        return self.data[-1]

    def _load_csv(self, filename):
        print(f"[Sim] Parsing {filename}...")
        with open(filename, 'r', encoding='utf-8-sig', errors='ignore') as f:
            lines = f.readlines()
        
        header_index = -1; header_map = {}; converters = {}
        keys = {
            'time': ['time', 'timestamp'],
            'alt': ['state - pz', 'pos_z', 'position z', 'altitude', 'alt asl', 'alt agl', 'height', 'disp z'],
            'acc_x': ['accx', 'acc_x', 'acc x', 'acceleration x'],
            'acc_y': ['accy', 'acc_y', 'acc y', 'acceleration y'],
            'acc_z': ['accz', 'acc_z', 'acc z', 'acceleration z', 'vertical acc'],
            'gyro_x': ['gyrox', 'gyro_x', 'gyro x'],
            'gyro_y': ['gyroy', 'gyro_y', 'gyro y'],
            'gyro_z': ['gyroz', 'gyro_z', 'gyro z'],
            'mag_x': ['magx', 'mag_x', 'mag x'],
            'mag_y': ['magy', 'mag_y', 'mag y'],
            'mag_z': ['magz', 'mag_z', 'mag z'],
            'lat': ['latitude', ' lat'],
            'lon': ['longitude', ' lon'],
            'gps_alt': ['gps - alt', 'gps alt', ' max-m10s - alt', 'mockgps - alt', 'alt (m)'],
            'fix': ['fix quality', 'fix', 'gps fix'],
            'sats': ['satellites', 'num sats', 'sats'],
            'heading': ['heading', 'course'],
            'truth_acc_z': ['truth accel', 'true accel', 'inertial accel'],
            'pres': ['pressure', 'baro', 'pres'],
            'temp': ['temperature', 'temp'],
        }

        for i, line in enumerate(lines):
            clean_parts = [p.lower().replace('#','').replace('"','').strip() for p in line.split(',')]
            if len(clean_parts) < 2: continue
            found_cols = {}
            for col_idx, col_name in enumerate(clean_parts):
                for key_type, keywords in keys.items():
                    if any(k in col_name for k in keywords) and key_type not in found_cols:
                        found_cols[key_type] = col_idx
                        converters[key_type] = lambda x: x
                        if key_type == 'temp' and 'f' in col_name and 'c' not in col_name:
                            converters[key_type] = lambda x: (x - 32.0) * 5.0/9.0
                        elif key_type == 'alt' and ('ft' in col_name or 'feet' in col_name):
                            converters[key_type] = lambda x: x * 0.3048
                        elif key_type in ['acc_x', 'acc_y', 'acc_z'] and ('g' in col_name and 'mag' not in col_name):
                            converters[key_type] = lambda x: x * 9.80665
                        elif key_type in ['gyro_x', 'gyro_y', 'gyro_z'] and ('deg' in col_name and 'rad' not in col_name):
                            converters[key_type] = lambda x: x * np.pi / 180.0

            if 'time' in found_cols and 'alt' in found_cols:
                header_index = i; header_map = found_cols
                print(f"[Sim] Found Header at line {i+1}. Map: {header_map}")
                break
        
        if header_index == -1: raise ValueError("Headers not found.")

        # Detect OpenRocket format: check if first data row has near-zero acceleration
        # OpenRocket reports inertial acceleration (gravity removed), so we need to add it back
        # Real flight data already has specific force, so we don't add gravity
        for i in range(header_index + 1, len(lines)):
            line = lines[i].strip()
            if not line or line.startswith('#'): continue
            first_data_row = line.split(',')
            try:
                # Check any available acc axis for OpenRocket detection
                for acc_key in ['acc_z', 'acc_x', 'acc_y']:
                    if acc_key in header_map and header_map[acc_key] < len(first_data_row):
                        first_acc = converters[acc_key](float(first_data_row[header_map[acc_key]].strip()))
                        # OpenRocket starts at 0 inertial accel (at rest), so abs value should be < 1
                        if abs(first_acc) < 0.005:
                            self.is_openrocket = True
                            print("[Sim] Detected OpenRocket format (inertial accel). Adding gravity to convert to specific force.")
                        else:
                            print("[Sim] Detected real flight data format (specific force). Using values as-is.")
                        break
                break
            except:
                break

        count = 0
        for i in range(header_index + 1, len(lines)):
            line = lines[i].strip()
            if not line or line.startswith('#'): continue
            row = line.split(',')
            try:
                def get_val(k, d=0.0):
                    return converters[k](float(row[header_map[k]].strip())) if k in header_map and header_map[k] < len(row) else d

                # Load all three accelerometer axes
                sensor_x = get_val('acc_x')
                sensor_y = get_val('acc_y')
                sensor_z = get_val('acc_z')
                gyro_x = get_val('gyro_x')
                gyro_y = get_val('gyro_y')
                gyro_z = get_val('gyro_z')
                mag_x = get_val('mag_x')
                mag_y = get_val('mag_y')
                mag_z = get_val('mag_z')

                # If OpenRocket format, add gravity to convert inertial accel -> specific force
                # (typically gravity is on the Z axis)
                if self.is_openrocket:
                    sensor_z += 9.81

                alt_val = get_val('alt')
                truth_acc = get_val('truth_acc_z', 0.0)
                lat_val = get_val('lat', 45.0)
                lon_val = get_val('lon', -122.0)
                gps_alt_val = get_val('gps_alt', alt_val)
                fix_val = int(get_val('fix', 1.0))
                sats_val = int(get_val('sats', 8.0))
                heading_val = get_val('heading', 0.0)

                self.data.append(PacketData(get_val('time'),
                                            np.array([sensor_x, sensor_y, sensor_z]),
                                            np.array([gyro_x, gyro_y, gyro_z]),
                                            np.array([mag_x, mag_y, mag_z]),
                                            get_val('pres', 1013.25),
                                            get_val('temp', 25.0),
                                            lat_val,
                                            lon_val,
                                            gps_alt_val,
                                            fix_val,
                                            sats_val,
                                            heading_val,
                                            truth_alt=alt_val,
                                            truth_accel=truth_acc))
                count += 1
            except: continue
        print(f"[Sim] Successfully loaded {count} rows.")

class NetworkStreamSim(DataSource):
    def __init__(self, port=9000):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', port))
        self.sock.setblocking(False)
        self.last_packet = PacketData(0, np.zeros(3), np.zeros(3), np.zeros(3), 1013, 25, 0,0,0, 1, 8, 0)
        print(f"[Sim] Listening for UDP data on port {port}")
    def get_next_packet(self) -> PacketData:
        try:
            data, _ = self.sock.recvfrom(4096)
            parts = data.decode().split(',')
            if len(parts) >= 5:
                self.last_packet.timestamp = float(parts[0])
                self.last_packet.accel = np.array([float(parts[1]), float(parts[2]), float(parts[3])])
                self.last_packet.alt = float(parts[4])
        except BlockingIOError: pass
        return self.last_packet

class PadDelaySim(DataSource):
    """Wraps another DataSource and adds pad idle time before starting the simulation.
    This allows the FC to settle and calibrate before flight begins."""

    # Pad delay constant - time to hold on pad before starting sim
    PAD_DELAY = 5.0  # seconds

    def __init__(self, source: DataSource):
        self.source = source
        self.elapsed_time = 0.0
        self.dt = 0.02  # Assume 50Hz
        self.pad_packet = None  # Store first packet for repeating
        self.pad_complete = False
        print(f"[Sim] Adding {self.PAD_DELAY}s pad delay (allows FC to settle)")

    def is_finished(self) -> bool:
        return self.pad_complete and self.source.is_finished()

    def get_next_packet(self) -> PacketData:
        # During pad delay, repeat the first packet
        if self.elapsed_time < self.PAD_DELAY:
            if self.pad_packet is None:
                # Get the first packet from source
                self.pad_packet = self.source.get_next_packet()
                # Adjust timestamp to 0
                self.pad_packet.timestamp = 0.0

            # Return a copy with updated timestamp
            packet = PacketData(
                timestamp=self.elapsed_time,
                accel=self.pad_packet.accel.copy(),
                gyro=self.pad_packet.gyro.copy(),
                mag=self.pad_packet.mag.copy(),
                pressure=self.pad_packet.pressure,
                temp=self.pad_packet.temp,
                lat=self.pad_packet.lat,
                lon=self.pad_packet.lon,
                alt=self.pad_packet.alt,
                fix=self.pad_packet.fix,
                sats=self.pad_packet.sats,
                heading=self.pad_packet.heading,
                truth_alt=self.pad_packet.truth_alt
            )

            self.elapsed_time += self.dt
            return packet
        else:
            # Pad delay complete, pass through source packets with adjusted timestamp
            self.pad_complete = True
            # Don't print message - disrupts the simulation table flow

            packet = self.source.get_next_packet()
            packet.timestamp += self.PAD_DELAY
            return packet

class RotatedSim(DataSource):
    """Wraps another DataSource and applies a 90-degree axis rotation to sensor data."""
    def __init__(self, source: DataSource, rotation_deg=None):
        self.source = source

        if rotation_deg is None:
            # Generate random 90-degree rotation (simulates different sensor mounting)
            # Pick a random axis permutation (24 possible orientations)
            rotations_90deg = [
                (0, 0, 0),      # Identity (no rotation)
                (90, 0, 0),     # X-axis rotations
                (180, 0, 0),
                (270, 0, 0),
                (0, 90, 0),     # Y-axis rotations
                (0, 180, 0),
                (0, 270, 0),
                (0, 0, 90),     # Z-axis rotations
                (0, 0, 180),
                (0, 0, 270),
                (90, 90, 0),    # Two-axis combinations
                (90, 270, 0),
                (270, 90, 0),
                (270, 270, 0),
                (90, 0, 90),
                (90, 0, 270),
                (270, 0, 90),
                (270, 0, 270),
                (0, 90, 90),
                (0, 90, 270),
                (0, 270, 90),
                (0, 270, 270),
            ]

            rotation_deg = rotations_90deg[np.random.randint(0, len(rotations_90deg))]
            self.rotation = Rotation.from_euler('xyz', rotation_deg, degrees=True)

            print(f"[Sim] Applying random 90° rotation: {rotation_deg}")
        else:
            # Use specified rotation
            self.rotation = Rotation.from_euler('xyz', rotation_deg, degrees=True)
            print(f"[Sim] Applying specified rotation: {rotation_deg}")

    def is_finished(self) -> bool:
        return self.source.is_finished()

    def get_next_packet(self) -> PacketData:
        packet = self.source.get_next_packet()

        # Preserve ground truth altitude (rotation doesn't affect altitude)
        if packet.truth_alt is None:
            packet.truth_alt = packet.alt

        # Rotate accelerometer data (specific force)
        packet.accel = self.rotation.apply(packet.accel)

        # Rotate gyroscope data (angular velocity)
        packet.gyro = self.rotation.apply(packet.gyro)

        # Rotate magnetometer data
        packet.mag = self.rotation.apply(packet.mag)

        return packet

class NoisySim(DataSource):
    """Wraps another DataSource and adds Gaussian noise to sensor data."""
    def __init__(self, source: DataSource,
                 accel_noise=0.05, gyro_noise=0.01, mag_noise=0.5, baro_noise=0.5):
        """
        Args:
            source: DataSource to wrap
            accel_noise: Accelerometer noise std dev (m/s²)
            gyro_noise: Gyroscope noise std dev (rad/s)
            mag_noise: Magnetometer noise std dev (uT)
            baro_noise: Barometer noise std dev (hPa)
        """
        self.source = source
        self.accel_noise = accel_noise
        self.gyro_noise = gyro_noise
        self.mag_noise = mag_noise
        self.baro_noise = baro_noise

        print(f"[Sim] Applying Gaussian noise:")
        print(f"      Accel: {accel_noise:.3f} m/s², Gyro: {gyro_noise:.3f} rad/s")
        print(f"      Mag: {mag_noise:.1f} uT, Baro: {baro_noise:.1f} hPa")

    def is_finished(self) -> bool:
        return self.source.is_finished()

    def get_next_packet(self) -> PacketData:
        packet = self.source.get_next_packet()

        # Preserve ground truth altitude before adding noise
        if packet.truth_alt is None:
            packet.truth_alt = packet.alt

        # Add Gaussian noise to each sensor
        packet.accel += np.random.normal(0, self.accel_noise, 3)
        packet.gyro += np.random.normal(0, self.gyro_noise, 3)
        packet.mag += np.random.normal(0, self.mag_noise, 3)

        # Add noise to pressure and convert to altitude
        # Using standard barometric formula: alt = 44330 * (1 - (P/P0)^0.1903)
        P0 = 1013.25  # Sea level pressure in hPa
        packet.pressure += np.random.normal(0, self.baro_noise)
        packet.alt = 44330.0 * (1.0 - (packet.pressure / P0) ** 0.1903)

        return packet
