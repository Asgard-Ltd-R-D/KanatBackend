# ui_client.py
import tkinter as tk
from tkinter import ttk, messagebox
import socket
import struct
import time
import protocol # Import our shared module

# ===============================
# Version Information
# ===============================
__version__ = "1.1.0" # Added LRF controls
__updated__ = "2025-10-20"

# ===============================
# UI Constants
# ===============================
HOST = '132.8.7.125'
PORT = 4949
POLL_INTERVAL_MS = 30
AXIS_ID = 1
SYSTEM_AXIS_ID = 0 # For system-level commands like LRF

class TCPClient:
    """Helper class to manage the TCP connection and protocol."""
    def __init__(self):
        self.sock = None
        self.buffer = b''

    def connect(self, host, port):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Bind client side to the fake local IP
            self.sock.bind(('132.8.7.1', 0))  # 0 means choose any source port
            self.sock.settimeout(2)
            self.sock.connect((host, port))
            self.sock.settimeout(1.0)
                
            pkt = protocol.build_packet(0x00, SYSTEM_AXIS_ID, protocol.NAME_TO_OPCODE["COM_Connect"])
            self.sock.sendall(pkt)
            reply = self.sock.recv(1024)
            return reply == protocol.ACK_REPLY
        except Exception as e:
            print(f"[Client] Connection failed: {e}")
            self.sock = None
            return False

    def disconnect(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def send_command(self, opcode, axis_id, data=None):
        if not self.sock:
            return False
        try:
            pkt = protocol.build_packet(0x00, axis_id, opcode, data)
            self.sock.sendall(pkt)
            reply = self.sock.recv(1024)
            if reply == protocol.ACK_REPLY:
                return True
            else:
                print(f"[Client] Sent {opcode:04X}, but got non-ACK reply: {reply.hex()}")
                return False
        except Exception as e:
            print(f"[Client] Error in send_command: {e}")
            self.disconnect()
            return False

    def request_data(self, opcode, axis_id):
        if not self.sock:
            return None
        try:
            pkt = protocol.build_packet(0x00, axis_id, opcode, None)
            self.sock.sendall(pkt)
            
            while True:
                data = self.sock.recv(1024)
                if not data:
                    self.disconnect()
                    return None
                
                self.buffer += data
                pkt, self.buffer = protocol.parse_packet(self.buffer)
                
                if pkt:
                    data_field = pkt[7:-1]
                    if len(data_field) == 4:
                        value = struct.unpack(">f", data_field)[0]
                        return value
                    else:
                        print(f"[Client] Got reply, but unexpected data length: {len(data_field)}")
                        return None

        except Exception as e:
            print(f"[Client] Error in request_data: {e}")
            self.disconnect()
            return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Motion UI Client v{__version__}")
        self.geometry("350x500")
        
        self.client = TCPClient()
        self.is_connected = False
        self._polling_job = None

        self.status_var = tk.StringVar(value="Status: Disconnected")
        self.pos_var = tk.StringVar(value="Pos: 0.00")
        self.speed_var = tk.StringVar(value="Speed: 0.00")
        self.lrf_range_var = tk.StringVar(value="LRF Range: 0.00 m")
        self.lrf_set_range_var = tk.StringVar(value="100.0")
        self.target_pos_var = tk.StringVar(value="10.0")
        self.speed_cmd_var = tk.StringVar(value="5.0")
        self.accel_cmd_var = tk.StringVar(value="10.0")

        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        conn_frame = ttk.LabelFrame(main_frame, text="Connection")
        conn_frame.pack(fill=tk.X, pady=5)
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT, padx=5, pady=5)
        self.status_label = ttk.Label(conn_frame, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT, padx=5)

        status_frame = ttk.LabelFrame(main_frame, text="Axis 1 Status")
        status_frame.pack(fill=tk.X, pady=5)
        ttk.Label(status_frame, textvariable=self.pos_var, font=("Consolas", 14)).pack(pady=2)
        ttk.Label(status_frame, textvariable=self.speed_var, font=("Consolas", 14)).pack(pady=2)

        lrf_frame = ttk.LabelFrame(main_frame, text="Laser Range Finder")
        lrf_frame.pack(fill=tk.X, pady=5, ipady=5)
        ttk.Label(lrf_frame, textvariable=self.lrf_range_var, font=("Consolas", 14)).pack(pady=2)
        lrf_cmd_frame = ttk.Frame(lrf_frame)
        lrf_cmd_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(lrf_cmd_frame, text="Set Range (m):").pack(side=tk.LEFT)
        ttk.Entry(lrf_cmd_frame, textvariable=self.lrf_set_range_var, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(lrf_cmd_frame, text="Set", command=self.send_lrf_set_range).pack(side=tk.LEFT)

        cmd_frame = ttk.LabelFrame(main_frame, text="Motion Commands")
        cmd_frame.pack(fill=tk.X, pady=5)
        
        cmd_grid = ttk.Frame(cmd_frame)
        cmd_grid.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(cmd_grid, text="Target Position:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(cmd_grid, textvariable=self.target_pos_var).grid(row=0, column=1, sticky=tk.EW)
        
        ttk.Label(cmd_grid, text="Max Speed:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(cmd_grid, textvariable=self.speed_cmd_var).grid(row=1, column=1, sticky=tk.EW)

        ttk.Label(cmd_grid, text="Acceleration:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(cmd_grid, textvariable=self.accel_cmd_var).grid(row=2, column=1, sticky=tk.EW)
        
        cmd_grid.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(cmd_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Send Absolute Move", command=self.send_abs_move).pack(fill=tk.X, expand=True, padx=5, pady=2)
        ttk.Button(btn_frame, text="Send Relative Move", command=self.send_rel_move).pack(fill=tk.X, expand=True, padx=5, pady=2)
        
    def toggle_connection(self):
        if not self.is_connected:
            if self.client.connect(HOST, PORT):
                self.is_connected = True
                self.status_var.set(f"Status: Connected to {HOST}:{PORT}")
                self.connect_btn.config(text="Disconnect")
                self.start_polling()
            else:
                messagebox.showerror("Error", f"Failed to connect to {HOST}:{PORT}")
        else:
            self.stop_polling()
            self.client.disconnect()
            self.is_connected = False
            self.status_var.set("Status: Disconnected")
            self.connect_btn.config(text="Connect")
            self.pos_var.set("Pos: 0.00")
            self.speed_var.set("Speed: 0.00")
            self.lrf_range_var.set("LRF Range: 0.00 m")

    def start_polling(self):
        if self._polling_job:
            self.after_cancel(self._polling_job)
        self.poll_for_status()

    def stop_polling(self):
        if self._polling_job:
            self.after_cancel(self._polling_job)
            self._polling_job = None

    def poll_for_status(self):
        if not self.is_connected:
            return

        pos = self.client.request_data(protocol.NAME_TO_OPCODE["MOT_GetLoadPosition"], AXIS_ID)
        if pos is None:
            self.toggle_connection()
            return
        self.pos_var.set(f"Pos: {pos:.2f}")
            
        spd = self.client.request_data(protocol.NAME_TO_OPCODE["MOT_GetMotorSpeed"], AXIS_ID)
        if spd is None:
            self.toggle_connection()
            return
        self.speed_var.set(f"Speed: {spd:.2f}")

        lrf_range = self.client.request_data(protocol.NAME_TO_OPCODE["LRF_GetRange"], SYSTEM_AXIS_ID)
        if lrf_range is None:
            self.toggle_connection()
            return
        self.lrf_range_var.set(f"LRF Range: {lrf_range:.2f} m")

        self._polling_job = self.after(POLL_INTERVAL_MS, self.poll_for_status)

    def send_lrf_set_range(self):
        if not self.is_connected:
            messagebox.showwarning("Warning", "Not connected.")
            return
        try:
            range_val = float(self.lrf_set_range_var.get())
            range_data = list(struct.pack(">f", range_val))
            success = self.client.send_command(
                protocol.NAME_TO_OPCODE["LRF_SetRange"], SYSTEM_AXIS_ID, range_data
            )
            if not success:
                messagebox.showerror("Error", "Failed to send LRF_SetRange command.")
                if not self.client.sock: self.toggle_connection()
        except ValueError:
            messagebox.showerror("Error", "Invalid range. Please enter a number.")


    def send_move_command(self, move_opcode):
        if not self.is_connected:
            messagebox.showwarning("Warning", "Not connected.")
            return
        
        try:
            target_pos = float(self.target_pos_var.get())
            speed = float(self.speed_cmd_var.get())
            accel = float(self.accel_cmd_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid input. Please enter numbers.")
            return
            
        success = True
        
        if not self.client.send_command(protocol.NAME_TO_OPCODE["MOT_SetPositionMode"], AXIS_ID):
            success = False
            
        if success:
            accel_data = list(struct.pack(">f", accel))
            if not self.client.send_command(protocol.NAME_TO_OPCODE["MOT_SetAcceleration"], AXIS_ID, accel_data):
                success = False

        if success:
            speed_data = list(struct.pack(">f", speed))
            if not self.client.send_command(protocol.NAME_TO_OPCODE["MOT_SetSpeed"], AXIS_ID, speed_data):
                success = False
        
        if success:
            pos_data = list(struct.pack(">f", target_pos))
            if not self.client.send_command(move_opcode, AXIS_ID, pos_data):
                success = False

        if success:
            if not self.client.send_command(protocol.NAME_TO_OPCODE["MOT_Update"], AXIS_ID):
                success = False

        if not success:
            messagebox.showerror("Error", "Failed to send command. Check connection.")
            if not self.client.sock: self.toggle_connection()
        else:
            print("[Client] Move sequence sent successfully.")
            
    def send_abs_move(self):
        self.send_move_command(protocol.NAME_TO_OPCODE["MOT_SetPositionAbsolute"])
        
    def send_rel_move(self):
        self.send_move_command(protocol.NAME_TO_OPCODE["MOT_SetPositionRelative"])

    def on_closing(self):
        self.stop_polling()
        self.client.disconnect()
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()

