# motion_simulator.py
import socket
import threading
import time
import struct
import protocol # Import our shared module

# ===============================
# Version Information
# ===============================
__version__ = "1.1.0" # Added LRF simulation
__updated__ = "2025-10-20"

# ===============================
# Server Constants
# ===============================
HOST = '132.8.7.125'
PORT = 4949
SIM_UPDATE_INTERVAL = 0.01 # 10ms simulation tick

class SimpleAxis:
    """A class to simulate a single motion axis."""
    def __init__(self, axis_id):
        self.axis_id = axis_id
        self.current_position = 0.0
        self.current_speed = 0.0
        self.target_position = 0.0
        self.max_speed = 10.0  # units/sec
        self.acceleration = 20.0 # units/sec^2 (not fully used in this simple sim)
        self.is_in_position_mode = True
        self.lock = threading.Lock()

    def update(self):
        """Simple physics update logic."""
        with self.lock:
            delta = self.target_position - self.current_position
            
            if abs(delta) < 0.01:
                self.current_speed = 0.0
                self.current_position = self.target_position
                return

            move_step = self.max_speed * SIM_UPDATE_INTERVAL
            
            if delta > 0:
                step = min(move_step, delta)
                self.current_position += step
                self.current_speed = self.max_speed
            else:
                step = max(-move_step, delta)
                self.current_position += step
                self.current_speed = -self.max_speed

    def set_target_abs(self, pos):
        with self.lock:
            self.target_position = pos
            print(f"[Axis {self.axis_id}] New absolute target: {pos:.2f}")

    def set_target_rel(self, rel_pos):
        with self.lock:
            self.target_position += rel_pos
            print(f"[Axis {self.axis_id}] New relative target (+{rel_pos:.2f}): {self.target_position:.2f}")

    def set_speed(self, speed):
        with self.lock:
            self.max_speed = abs(speed)
            print(f"[Axis {self.axis_id}] Max speed set to: {self.max_speed:.2f}")
            
    def set_accel(self, accel):
        with self.lock:
            self.acceleration = abs(accel)
            print(f"[Axis {self.axis_id}] Accel set to: {self.acceleration:.2f}")

    def get_position(self):
        with self.lock:
            return self.current_position

    def get_speed(self):
        with self.lock:
            return self.current_speed

# --- Global Simulator State ---
simulated_axis_1 = SimpleAxis(axis_id=1)
simulated_lrf_range = 0.0
lrf_lock = threading.Lock()

def handle_client(conn, addr):
    print(f"[Server] Connected by {addr}")
    global simulated_lrf_range
    try:
        buffer = b''
        while True:
            data = conn.recv(1024)
            if not data:
                break
            
            print(f"[Server-RX-DEBUG] Received raw bytes: {data.hex(' ')}")
            buffer += data
            
            while True:
                packet, buffer = protocol.parse_packet(buffer)
                if packet is None:
                    break

                print(f"[Server-RX-DEBUG] Parsed valid packet: {packet.hex(' ')}")
                
                axis_id = packet[4]
                opcode = (packet[5] << 8) | packet[6]
                data_field = packet[7:-1]
                
                # --- Handle System-Level Opcodes (Axis 0) ---
                if axis_id == 0:
                    if opcode == protocol.NAME_TO_OPCODE["COM_Connect"]:
                        print(f"[Server] Received COM_Connect for Axis 0. Acknowledging.")
                        print(f"[Server-TX-DEBUG] Sending ACK")
                        conn.sendall(protocol.ACK_REPLY)
                    elif opcode == protocol.NAME_TO_OPCODE["LRF_GetRange"]:
                        with lrf_lock:
                            current_range = simulated_lrf_range
                        reply_data = struct.pack(">f", current_range)
                        reply_pkt = protocol.build_reply_packet(0x00, axis_id, opcode, list(reply_data))
                        print(f"[Server-TX-DEBUG] Sending LRF_GetRange reply: {reply_pkt.hex(' ')}")
                        conn.sendall(reply_pkt)
                    elif opcode == protocol.NAME_TO_OPCODE["LRF_SetRange"]:
                        new_range = struct.unpack(">f", data_field)[0]
                        with lrf_lock:
                            simulated_lrf_range = new_range
                        print(f"[Server] LRF range set to: {new_range:.2f}")
                        print(f"[Server-TX-DEBUG] Sending ACK")
                        conn.sendall(protocol.ACK_REPLY)
                    else:
                        print(f"[Server] Ignoring unsupported command for Axis 0: {opcode:04X}")
                        print(f"[Server-TX-DEBUG] Sending ACK")
                        conn.sendall(protocol.ACK_REPLY)
                
                # --- Handle Axis 1 Specific Opcodes ---
                elif axis_id == 1:
                    if opcode == protocol.NAME_TO_OPCODE["MOT_GetLoadPosition"]:
                        pos = simulated_axis_1.get_position()
                        reply_data = struct.pack(">f", pos)
                        reply_pkt = protocol.build_reply_packet(0x00, axis_id, opcode, list(reply_data))
                        print(f"[Server-TX-DEBUG] Sending reply: {reply_pkt.hex(' ')}")
                        conn.sendall(reply_pkt)
                    
                    elif opcode == protocol.NAME_TO_OPCODE["MOT_GetMotorSpeed"]:
                        spd = simulated_axis_1.get_speed()
                        reply_data = struct.pack(">f", spd)
                        reply_pkt = protocol.build_reply_packet(0x00, axis_id, opcode, list(reply_data))
                        print(f"[Server-TX-DEBUG] Sending reply: {reply_pkt.hex(' ')}")
                        conn.sendall(reply_pkt)

                    elif opcode == protocol.NAME_TO_OPCODE["MOT_SetPositionAbsolute"]:
                        pos = struct.unpack(">f", data_field)[0]
                        simulated_axis_1.set_target_abs(pos)
                        print(f"[Server-TX-DEBUG] Sending ACK")
                        conn.sendall(protocol.ACK_REPLY)

                    elif opcode == protocol.NAME_TO_OPCODE["MOT_SetPositionRelative"]:
                        rel_pos = struct.unpack(">f", data_field)[0]
                        simulated_axis_1.set_target_rel(rel_pos)
                        print(f"[Server-TX-DEBUG] Sending ACK")
                        conn.sendall(protocol.ACK_REPLY)
                        
                    elif opcode == protocol.NAME_TO_OPCODE["MOT_SetSpeed"]:
                        speed = struct.unpack(">f", data_field)[0]
                        simulated_axis_1.set_speed(speed)
                        print(f"[Server-TX-DEBUG] Sending ACK")
                        conn.sendall(protocol.ACK_REPLY)

                    elif opcode == protocol.NAME_TO_OPCODE["MOT_SetAcceleration"]:
                        accel = struct.unpack(">f", data_field)[0]
                        simulated_axis_1.set_accel(accel)
                        print(f"[Server-TX-DEBUG] Sending ACK")
                        conn.sendall(protocol.ACK_REPLY)
                        
                    elif opcode in [
                        protocol.NAME_TO_OPCODE["MOT_SetPositionMode"],
                        protocol.NAME_TO_OPCODE["MOT_Update"]
                    ]:
                        print(f"[Server-TX-DEBUG] Sending ACK")
                        conn.sendall(protocol.ACK_REPLY)
                        
                    else:
                        print(f"[Server] Unhandled Opcode for Axis 1: {opcode:04X}")
                        print(f"[Server-TX-DEBUG] Sending ACK")
                        conn.sendall(protocol.ACK_REPLY)

                else:
                    print(f"[Server] Ignoring command for un-simulated Axis {axis_id}")
                    print(f"[Server-TX-DEBUG] Sending ACK")
                    conn.sendall(protocol.ACK_REPLY)

    except (ConnectionResetError, BrokenPipeError):
        print(f"[Server] Client {addr} disconnected abruptly.")
    finally:
        print(f"[Server] Closing connection to {addr}")
        conn.close()

def simulation_loop():
    while True:
        simulated_axis_1.update()
        time.sleep(SIM_UPDATE_INTERVAL)

def main():
    sim_thread = threading.Thread(target=simulation_loop, daemon=True)
    sim_thread.start()
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"[Server] Motion Simulator v{__version__} ({__updated__}) listening on {HOST}:{PORT}...")
        
        while True:
            conn, addr = s.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            client_thread.start()

if __name__ == "__main__":
    main()

