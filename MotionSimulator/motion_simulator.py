# motion_simulator.py
import socket
import threading
import time
import struct
import protocol # Import our shared module
import random

# ===============================
# Version Information
# ===============================
__version__ = "1.3.0" # Added CMER logic, Axis On/Off/Reset, Ballistic Offset
__updated__ = "2025-10-25"

# ===============================
# Server Constants
# ===============================
HOST = '132.8.7.125'
PORT = 5001
SIM_UPDATE_INTERVAL = 0.01 # 10ms simulation tick

# Simulated Axes
SIMULATED_AXES = [1, 2, 4, 5]

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
        self.is_on = False  # Axis state
        self.is_faulted = False # Axis fault state
        self.is_motion_complete = True # Motion status (Bit 2 of CMER)
        self.ballistic_offset = 0.0 # Ballistic offset state (Axis 1 and 2 only)
        self.lock = threading.Lock()

    def update(self):
        """Simple physics update logic. Runs only if axis is ON and not faulted."""
        with self.lock:
            if not self.is_on or self.is_faulted:
                self.current_speed = 0.0
                self.is_motion_complete = True
                return
            
            delta = self.target_position - self.current_position
            
            if abs(delta) < 0.01:
                self.current_speed = 0.0
                self.current_position = self.target_position
                self.is_motion_complete = True
                return

            self.is_motion_complete = False
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
            self.is_motion_complete = False
            print(f"[Axis {self.axis_id}] New absolute target: {pos:.2f}")

    def set_target_rel(self, rel_pos):
        with self.lock:
            self.target_position += rel_pos
            self.is_motion_complete = False
            print(f"[Axis {self.axis_id}] New relative target (+{rel_pos:.2f}): {self.target_position:.2f}")

    def set_speed(self, speed):
        with self.lock:
            self.max_speed = abs(speed)
            print(f"[Axis {self.axis_id}] Max speed set to: {self.max_speed:.2f}")
            
    def set_accel(self, accel):
        with self.lock:
            self.acceleration = abs(accel)
            print(f"[Axis {self.axis_id}] Accel set to: {self.acceleration:.2f}")
            
    def set_axis_on(self):
        with self.lock:
            self.is_on = True
            self.is_faulted = False
            print(f"[Axis {self.axis_id}] State set to ON")

    def set_axis_off(self):
        with self.lock:
            self.is_on = False
            self.current_speed = 0.0
            print(f"[Axis {self.axis_id}] State set to OFF")

    def set_axis_reset(self):
        with self.lock:
            self.is_faulted = False
            print(f"[Axis {self.axis_id}] Faults reset")

    def set_ballistic_offset(self, offset):
        with self.lock:
            self.ballistic_offset = offset
            print(f"[Axis {self.axis_id}] Ballistic Offset set to: {offset:.4f}")

    def get_ballistic_offset(self):
        with self.lock:
            return self.ballistic_offset
            
    def get_position(self):
        with self.lock:
            return self.current_position

    def get_speed(self):
        with self.lock:
            return self.current_speed
            
    def get_voltage(self):
        # Simulate Voltage: 24.00V +- 0.2V
        return 24.0 + random.uniform(-0.2, 0.2)
        
    def get_current(self):
        # Simulate Current: 1.00A +- 0.5A. Higher current if axis is moving.
        base_current = 1.0 + random.uniform(-0.5, 0.5)
        if abs(self.current_speed) > 0.01:
            base_current += 0.5
        return max(0.0, base_current)
        
    def get_error_register(self):
        """
        Returns the 16-bit CMER (Capture Motor Error Register)
        Opcode: 0x0E0B
        """
        reg = 0
        
        # Bit 0: Fault status (1 = Fault)
        if self.is_faulted:
            reg |= 0x0001 
            
        # Bit 1: Axis status (1 = Axis on)
        if self.is_on:
            reg |= 0x0002
            
        # Bit 2: Motion is complete (1 = Motion complete)
        if self.is_motion_complete:
            reg |= 0x0004
            
        # Simulate a generic over-current if current > 2.0 (Bit 7)
        if self.get_current() > 2.0:
            reg |= 0x0080 
            
        # Simulate a CAN bus error if axis 5 (Bit 15)
        if self.axis_id == 5:
            reg |= 0x8000
            
        return reg

# --- Global Simulator State ---
simulated_axes = {id: SimpleAxis(axis_id=id) for id in SIMULATED_AXES}

# Initialize all axes to be off by default
for axis in simulated_axes.values():
    axis.set_axis_off()

simulated_lrf_range = 0.0
lrf_lock = threading.Lock()
is_sync_mode = False
is_inner_mode = False

def handle_client(conn, addr):
    print(f"[Server] Connected by {addr}")
    global simulated_lrf_range, is_sync_mode, is_inner_mode
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
                
                # --- Handle System-Level Opcodes (Axis 0 or DG/COM/LRF Groups) ---
                if axis_id == 0:
                    if opcode == protocol.NAME_TO_OPCODE["COM_Connect"]:
                        print(f"[Server] Received COM_Connect. Acknowledging.")
                        conn.sendall(protocol.ACK_REPLY)
                        
                    # LRF COMMANDS
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
                        conn.sendall(protocol.ACK_REPLY)
                        
                    # MODE CONTROL COMMANDS (DG Group)
                    elif opcode == protocol.NAME_TO_OPCODE["DG_SetSyncMode"]:
                        val = struct.unpack(">H", data_field)[0]
                        is_sync_mode = (val != 0)
                        is_inner_mode = False # Setting Sync mode overrides Inner/Outer
                        print(f"[Server] Mode set to: {'SYNC' if is_sync_mode else 'UNSYNC'}")
                        conn.sendall(protocol.ACK_REPLY)
                    elif opcode == protocol.NAME_TO_OPCODE["DG_SetInnerMode"]:
                        val = struct.unpack(">H", data_field)[0]
                        is_inner_mode = (val != 0)
                        if not is_sync_mode:
                            print(f"[Server] Unsync Mode set to: {'INNER' if is_inner_mode else 'OUTER'}")
                        conn.sendall(protocol.ACK_REPLY)
                        
                    else:
                        print(f"[Server] Ignoring unsupported command for Axis 0: {opcode:04X}")
                        conn.sendall(protocol.ACK_REPLY)
                
                # --- Handle Axis Specific Opcodes (Motion/Error) ---
                elif axis_id in simulated_axes:
                    axis = simulated_axes[axis_id]
                    
                    # --- Data Request Opcodes ---
                    if opcode == protocol.NAME_TO_OPCODE["MOT_GetLoadPosition"]:
                        pos = axis.get_position()
                        reply_data = struct.pack(">f", pos)
                        reply_pkt = protocol.build_reply_packet(0x00, axis_id, opcode, list(reply_data))
                        conn.sendall(reply_pkt)
                    
                    elif opcode == protocol.NAME_TO_OPCODE["MOT_GetMotorSpeed"]:
                        spd = axis.get_speed()
                        reply_data = struct.pack(">f", spd)
                        reply_pkt = protocol.build_reply_packet(0x00, axis_id, opcode, list(reply_data))
                        conn.sendall(reply_pkt)
                        
                    elif opcode == protocol.NAME_TO_OPCODE["MOT_GetMotorVoltage"]:
                        vol = axis.get_voltage()
                        reply_data = struct.pack(">f", vol)
                        reply_pkt = protocol.build_reply_packet(0x00, axis_id, opcode, list(reply_data))
                        conn.sendall(reply_pkt)
                        
                    elif opcode == protocol.NAME_TO_OPCODE["MOT_GetMotorCurrent"]:
                        cur = axis.get_current()
                        reply_data = struct.pack(">f", cur)
                        reply_pkt = protocol.build_reply_packet(0x00, axis_id, opcode, list(reply_data))
                        conn.sendall(reply_pkt)

                    elif opcode == protocol.NAME_TO_OPCODE["ERR_CaptureMotorErrorRegister"]:
                        cmer = axis.get_error_register()
                        # CMER is a 16-bit (2-byte) unsigned integer
                        reply_data = struct.pack(">H", cmer)
                        reply_pkt = protocol.build_reply_packet(0x00, axis_id, opcode, list(reply_data))
                        print(f"[Server-TX-DEBUG] Sending CMER ({cmer:04X}) reply: {reply_pkt.hex(' ')}")
                        conn.sendall(reply_pkt)
                        
                    elif opcode == protocol.NAME_TO_OPCODE["DG_GetBallisticOffset"]:
                        offset = axis.get_ballistic_offset()
                        reply_data = struct.pack(">f", offset)
                        reply_pkt = protocol.build_reply_packet(0x00, axis_id, opcode, list(reply_data))
                        conn.sendall(reply_pkt)
                    
                    # --- Command Set Opcodes ---
                    elif opcode == protocol.NAME_TO_OPCODE["MOT_SetPositionAbsolute"]:
                        pos = struct.unpack(">f", data_field)[0]
                        axis.set_target_abs(pos)
                        conn.sendall(protocol.ACK_REPLY)

                    elif opcode == protocol.NAME_TO_OPCODE["MOT_SetPositionRelative"]:
                        rel_pos = struct.unpack(">f", data_field)[0]
                        axis.set_target_rel(rel_pos)
                        conn.sendall(protocol.ACK_REPLY)
                        
                    elif opcode == protocol.NAME_TO_OPCODE["MOT_SetSpeed"]:
                        speed = struct.unpack(">f", data_field)[0]
                        axis.set_speed(speed)
                        conn.sendall(protocol.ACK_REPLY)

                    elif opcode == protocol.NAME_TO_OPCODE["MOT_SetAcceleration"]:
                        accel = struct.unpack(">f", data_field)[0]
                        axis.set_accel(accel)
                        conn.sendall(protocol.ACK_REPLY)
                        
                    elif opcode == protocol.NAME_TO_OPCODE["MOT_AxisOn"]:
                        axis.set_axis_on()
                        conn.sendall(protocol.ACK_REPLY)

                    elif opcode == protocol.NAME_TO_OPCODE["MOT_AxisOff"]:
                        axis.set_axis_off()
                        conn.sendall(protocol.ACK_REPLY)

                    elif opcode == protocol.NAME_TO_OPCODE["MOT_AxisReset"]:
                        axis.set_axis_reset()
                        conn.sendall(protocol.ACK_REPLY)
                        
                    elif opcode == protocol.NAME_TO_OPCODE["DG_SetBallisticOffset"]:
                        # Only applicable to Axis 1 and 2
                        if axis_id in [1, 2]:
                            offset = struct.unpack(">f", data_field)[0]
                            axis.set_ballistic_offset(offset)
                        else:
                            print(f"[Server] DG_SetBallisticOffset ignored for Axis {axis_id}")
                        conn.sendall(protocol.ACK_REPLY)
                        
                    elif opcode in [
                        protocol.NAME_TO_OPCODE["MOT_SetPositionMode"],
                        protocol.NAME_TO_OPCODE["MOT_Update"]
                    ]:
                        # Acknowledge commands that don't change internal state in this simple simulator
                        conn.sendall(protocol.ACK_REPLY)
                        
                    else:
                        print(f"[Server] Unhandled Opcode for Axis {axis_id}: {opcode:04X}")
                        conn.sendall(protocol.ACK_REPLY)

                else:
                    print(f"[Server] Ignoring command for un-simulated Axis {axis_id}")
                    conn.sendall(protocol.ACK_REPLY)

    except (ConnectionResetError, BrokenPipeError):
        print(f"[Server] Client {addr} disconnected abruptly.")
    finally:
        print(f"[Server] Closing connection to {addr}")
        conn.close()

def simulation_loop():
    """Runs the physics update loop for all simulated axes."""
    while True:
        for axis in simulated_axes.values():
            axis.update()
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
