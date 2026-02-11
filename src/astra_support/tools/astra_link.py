import serial
import socket
import time
from typing import Optional

class FlightComputerLink:
    """Base interface for connecting to the Flight Computer."""
    def send(self, data: bytes):
        raise NotImplementedError
    
    def read_line(self) -> Optional[str]:
        raise NotImplementedError
        
    def close(self):
        raise NotImplementedError

class SerialLink(FlightComputerLink):
    """HITL: Connect via USB Serial."""
    def __init__(self, port: str, baudrate: int = 115200):
        try:
            self.ser = serial.Serial(port, baudrate, timeout=0.01)
            print(f"[Link] Connected to Serial Port: {port}")
        except serial.SerialException as e:
            raise ConnectionError(f"Could not open serial port {port}: {e}")

    def send(self, data: bytes):
        try:
            self.ser.write(data)
        except serial.SerialException:
            raise ConnectionError("Serial cable disconnected")

    def read_line(self) -> Optional[str]:
        if self.ser.in_waiting:
            try:
                line = self.ser.readline()
                return line.decode('utf-8', errors='ignore').strip()
            except serial.SerialException as e:
                raise ConnectionError(f"Serial read error: {e}")
            except Exception:
                return None
        return None

    def close(self):
        if hasattr(self, 'ser') and self.ser.is_open:
            self.ser.close()

class TCPLink(FlightComputerLink):
    """SITL: Connect via TCP Socket (Server Mode)."""
    def __init__(self, host: str = '0.0.0.0', port: int = 5555):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(1)
        self.server.settimeout(1.0)  # 1 second timeout for accept

        print(f"[Link] SITL Server listening on {host}:{port}...")
        # Accept with timeout to allow Ctrl+C interruption
        self.conn = None
        try:
            while self.conn is None:
                try:
                    self.conn, addr = self.server.accept()
                    self.conn.setblocking(False) # Non-blocking for data transfer
                    print(f"[Link] Flight Software connected from {addr}")
                except socket.timeout:
                    # Timeout allows KeyboardInterrupt to be detected
                    continue
        except KeyboardInterrupt:
            self.server.close()
            raise ConnectionError("Connection interrupted by user")
        self._buffer = b''

    def send(self, data: bytes):
        try:
            self.conn.sendall(data)
        except (BrokenPipeError, ConnectionResetError):
            raise ConnectionError("TCP Connection reset by peer")

    def read_line(self) -> Optional[str]:
        try:
            chunk = self.conn.recv(4096)
            if chunk == b'': 
                # Empty bytes means the other side closed the connection cleanly
                raise ConnectionError("TCP Connection closed by Flight Computer")
            self._buffer += chunk
        except BlockingIOError:
            pass # No data waiting, that's fine
        except ConnectionError:
            raise # Re-raise known connection errors
        except Exception as e:
            # Catch other socket weirdness
            raise ConnectionError(f"Socket error: {e}")

        if b'\n' in self._buffer:
            line, self._buffer = self._buffer.split(b'\n', 1)
            return line.decode('utf-8', errors='ignore').strip()
        return None

    def close(self):
        if hasattr(self, 'conn'): self.conn.close()
        self.server.close()