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
__version__ = "1.4.0" # Added Axis ON/OFF status indicator
__updated__ = "2025-10-25"

# ===============================
# UI Constants
# ===============================
HOST = '132.8.7.125'
PORT = 5001
POLL_INTERVAL_MS = 30
SYSTEM_AXIS_ID = 0 # For system-level commands like LRF
SIMULATED_AXES = [1, 2, 4, 5]

class TCPClient:
    """Helper class to manage the TCP connection and protocol."""
    def __init__(self):
        self.sock = None
        self.buffer = b''

    def connect(self, host, port):
        try:
            # Create a socket and connect
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Bind client side to the fake local IP
            self.sock.bind(('132.8.7.1', 0))  # 0 means choose any source port
            self.sock.settimeout(2)
            self.sock.connect((host, port))
            self.sock.settimeout(1.0)
            
            # Send initial connection command (COM_Connect)
            pkt = protocol.build_packet(0x00, SYSTEM_AXIS_ID, protocol.NAME_TO_OPCODE["COM_Connect"])
            self.sock.sendall(pkt)
            
            # Wait for ACK reply
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
        """Sends a command expecting only an ACK reply."""
        if not self.sock:
            return False
        try:
            pkt = protocol.build_packet(0x00, axis_id, opcode, data)
            self.sock.sendall(pkt)
            self.sock.settimeout(0.5) # Temporarily shorten timeout for fast ACK
            reply = self.sock.recv(1024)
            self.sock.settimeout(1.0) # Reset timeout
            
            if reply == protocol.ACK_REPLY:
                return True
            else:
                print(f"[Client] Sent {opcode:04X}, but got non-ACK reply: {reply.hex()}")
                return False
        except Exception as e:
            print(f"[Client] Error in send_command (Op: {opcode:04X}): {e}")
            self.disconnect()
            return False

    def request_data(self, opcode, axis_id):
        """Sends a request expecting a data reply (float or uint16)."""
        if not self.sock:
            return None
        try:
            pkt = protocol.build_packet(0x00, axis_id, opcode, None)
            self.sock.sendall(pkt)
            
            # Loop to buffer incoming data until a full packet is parsed
            while True:
                data = self.sock.recv(1024)
                if not data:
                    self.disconnect()
                    return None
                
                self.buffer += data
                pkt, self.buffer = protocol.parse_packet(self.buffer)
                
                if pkt:
                    data_field = pkt[7:-1]
                    
                    # Determine unpacking based on opcode and data length
                    if opcode == protocol.NAME_TO_OPCODE["ERR_CaptureMotorErrorRegister"]:
                        # Expects 16-bit unsigned integer (2 bytes)
                        if len(data_field) == 2:
                            value = struct.unpack(">H", data_field)[0]
                            return value
                        else:
                            print(f"[Client] CMER reply, but unexpected data length: {len(data_field)}")
                            return None
                    
                    else:
                        # Default to 4-byte float for all other sensor/position data
                        if len(data_field) == 4:
                            value = struct.unpack(">f", data_field)[0]
                            return value
                        else:
                            print(f"[Client] Float reply, but unexpected data length: {len(data_field)}")
                            return None

        except Exception as e:
            print(f"[Client] Error in request_data (Op: {opcode:04X}): {e}")
            self.disconnect()
            return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Motion UI Client v{__version__}")
        self.geometry("800x600")
        
        self.client = TCPClient()
        self.is_connected = False
        self._polling_job = None

        # State Variables
        self.status_var = tk.StringVar(value="Status: Disconnected")
        self.lrf_range_var = tk.StringVar(value="LRF Range: 0.00 m")
        self.lrf_set_range_var = tk.StringVar(value="100.0")
        self.sync_mode_var = tk.IntVar(value=0) # 0=UNSYNC, 1=SYNC
        self.inner_mode_var = tk.IntVar(value=0) # 0=OUTER, 1=INNER
        
        # Motion Command Variables
        self.target_axis_var = tk.StringVar(value=SIMULATED_AXES[0])
        self.target_pos_var = tk.StringVar(value="10.0")
        self.speed_cmd_var = tk.StringVar(value="5.0")
        self.accel_cmd_var = tk.StringVar(value="10.0")
        self.ballistic_offset_var = tk.StringVar(value="0.0")


        # Data dictionary to hold dynamic status updates for each axis
        self.axis_data = {}
        for axis_id in SIMULATED_AXES:
            self.axis_data[axis_id] = {
                "pos": tk.StringVar(value="Pos: 0.00"),
                "spd": tk.StringVar(value="Speed: 0.00"),
                "vol": tk.StringVar(value="Volt: 0.00 V"),
                "cur": tk.StringVar(value="Curr: 0.00 A"),
                "cmer": tk.StringVar(value="CMER: 0000h"),
                "ballistic": tk.StringVar(value="B.Offset: N/A"),
                "on_indicator": None # Placeholder for the visual label
            }

        self._build_ui()

    def _build_ui(self):
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Left Control Frame ---
        control_frame = ttk.Frame(main_pane, padding="5 5 5 5")
        main_pane.add(control_frame, weight=1)

        self._create_connection_ui(control_frame).pack(fill=tk.X, pady=5)
        self._create_lrf_ui(control_frame).pack(fill=tk.X, pady=5)
        self._create_mode_control_ui(control_frame).pack(fill=tk.X, pady=5)
        self._create_motion_commands_ui(control_frame).pack(fill=tk.X, pady=5)
        self._create_axis_control_ui(control_frame).pack(fill=tk.X, pady=5)
        self._create_ballistic_offset_ui(control_frame).pack(fill=tk.X, pady=5)

        # --- Right Status Frame ---
        status_frame = ttk.Frame(main_pane, padding="5 5 5 5")
        main_pane.add(status_frame, weight=2)
        
        self._create_all_axis_status_ui(status_frame).pack(fill=tk.BOTH, expand=True)

    def _create_connection_ui(self, parent):
        conn_frame = ttk.LabelFrame(parent, text="Connection")
        conn_frame.pack(fill=tk.X)
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT, padx=5, pady=5)
        self.status_label = ttk.Label(conn_frame, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT, padx=5)
        return conn_frame

    def _create_lrf_ui(self, parent):
        lrf_frame = ttk.LabelFrame(parent, text="Laser Range Finder")
        ttk.Label(lrf_frame, textvariable=self.lrf_range_var, font=("Consolas", 12)).pack(pady=5)
        
        lrf_cmd_frame = ttk.Frame(lrf_frame)
        lrf_cmd_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(lrf_cmd_frame, text="Set Range (m):").pack(side=tk.LEFT)
        ttk.Entry(lrf_cmd_frame, textvariable=self.lrf_set_range_var, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(lrf_cmd_frame, text="Set", command=self.send_lrf_set_range).pack(side=tk.LEFT)
        return lrf_frame

    def _create_mode_control_ui(self, parent):
        mode_frame = ttk.LabelFrame(parent, text="Mode Control (Axis 0)")
        
        # Sync/Unsync
        sync_frame = ttk.Frame(mode_frame)
        sync_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(sync_frame, text="System Mode:").pack(side=tk.LEFT)
        ttk.Radiobutton(sync_frame, text="UNSYNC", variable=self.sync_mode_var, value=0, command=self.send_mode_control).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(sync_frame, text="SYNC", variable=self.sync_mode_var, value=1, command=self.send_mode_control).pack(side=tk.LEFT, padx=5)

        # Inner/Outer (Unsync only)
        self.inner_outer_frame = ttk.Frame(mode_frame)
        self.inner_outer_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(self.inner_outer_frame, text="Unsync Sub-Mode:").pack(side=tk.LEFT)
        ttk.Radiobutton(self.inner_outer_frame, text="OUTER", variable=self.inner_mode_var, value=0, command=self.send_mode_control_inner).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(self.inner_outer_frame, text="INNER", variable=self.inner_mode_var, value=1, command=self.send_mode_control_inner).pack(side=tk.LEFT, padx=5)
        
        self.sync_mode_var.trace_add("write", lambda *args: self.toggle_inner_outer_visibility())
        self.toggle_inner_outer_visibility()
        
        return mode_frame

    def toggle_inner_outer_visibility(self):
        """Hides/shows the Inner/Outer radio group based on Sync/Unsync state."""
        if self.sync_mode_var.get() == 0:  # Unsync mode
            self.inner_outer_frame.pack(fill=tk.X, padx=5, pady=2)
        else:
            self.inner_outer_frame.pack_forget()

    def _create_motion_commands_ui(self, parent):
        cmd_frame = ttk.LabelFrame(parent, text="Motion Commands")
        
        cmd_grid = ttk.Frame(cmd_frame)
        cmd_grid.pack(fill=tk.X, padx=5, pady=5)
        
        # Target Axis Selector
        ttk.Label(cmd_grid, text="Target Axis:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Combobox(cmd_grid, textvariable=self.target_axis_var, values=SIMULATED_AXES, state="readonly").grid(row=0, column=1, sticky=tk.EW)
        
        # Other inputs
        ttk.Label(cmd_grid, text="Target Position:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(cmd_grid, textvariable=self.target_pos_var).grid(row=1, column=1, sticky=tk.EW)
        
        ttk.Label(cmd_grid, text="Max Speed:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(cmd_grid, textvariable=self.speed_cmd_var).grid(row=2, column=1, sticky=tk.EW)

        ttk.Label(cmd_grid, text="Acceleration:").grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Entry(cmd_grid, textvariable=self.accel_cmd_var).grid(row=3, column=1, sticky=tk.EW)
        
        cmd_grid.columnconfigure(1, weight=1)

        # Move Buttons
        btn_frame = ttk.Frame(cmd_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Send Absolute Move", command=self.send_abs_move).pack(fill=tk.X, expand=True, padx=5, pady=2)
        ttk.Button(btn_frame, text="Send Relative Move", command=self.send_rel_move).pack(fill=tk.X, expand=True, padx=5, pady=2)
        
        return cmd_frame

    def _create_axis_control_ui(self, parent):
        control_frame = ttk.LabelFrame(parent, text="Axis Control (Selected Axis)")
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(btn_frame, text="Axis ON", command=lambda: self.send_axis_command("MOT_AxisOn")).pack(side=tk.LEFT, expand=True, padx=5)
        ttk.Button(btn_frame, text="Axis OFF", command=lambda: self.send_axis_command("MOT_AxisOff")).pack(side=tk.LEFT, expand=True, padx=5)
        ttk.Button(btn_frame, text="Axis RESET", command=lambda: self.send_axis_command("MOT_AxisReset")).pack(side=tk.LEFT, expand=True, padx=5)
        
        return control_frame

    def _create_ballistic_offset_ui(self, parent):
        offset_frame = ttk.LabelFrame(parent, text="Ballistic Offset (Axis 1, 2 Only)")
        
        offset_grid = ttk.Frame(offset_frame)
        offset_grid.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(offset_grid, text="Set Offset:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(offset_grid, textvariable=self.ballistic_offset_var).grid(row=0, column=1, sticky=tk.EW)
        ttk.Button(offset_grid, text="Send Offset", command=self.send_ballistic_offset).grid(row=0, column=2, padx=5)
        
        offset_grid.columnconfigure(1, weight=1)
        
        return offset_frame

    def _create_single_axis_status_panel(self, parent, axis_id):
        axis_frame = ttk.LabelFrame(parent)
        
        # Frame for Title and Indicator
        title_frame = ttk.Frame(axis_frame)
        title_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(title_frame, text=f"Axis {axis_id} Status", font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT)
        
        # Indicator Label (stores object reference in self.axis_data)
        self.axis_data[axis_id]["on_indicator"] = tk.Label(title_frame, text="ON/OFF", width=5, relief=tk.RAISED, bg='red', fg='white', font=("TkDefaultFont", 8))
        self.axis_data[axis_id]["on_indicator"].pack(side=tk.RIGHT)
        
        # Content
        ttk.Label(axis_frame, textvariable=self.axis_data[axis_id]["pos"], font=("Consolas", 12)).pack(anchor=tk.W, padx=5)
        ttk.Label(axis_frame, textvariable=self.axis_data[axis_id]["spd"], font=("Consolas", 12)).pack(anchor=tk.W, padx=5)
        
        status_sub_frame = ttk.Frame(axis_frame)
        status_sub_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(status_sub_frame, textvariable=self.axis_data[axis_id]["vol"], font=("Consolas", 10)).pack(side=tk.LEFT)
        ttk.Label(status_sub_frame, textvariable=self.axis_data[axis_id]["cur"], font=("Consolas", 10)).pack(side=tk.LEFT, padx=15)
        
        ttk.Label(axis_frame, textvariable=self.axis_data[axis_id]["cmer"], font=("Consolas", 10)).pack(anchor=tk.W, padx=5, pady=(2, 5))
        
        # Ballistic Offset display (only for Axis 1 and 2)
        if axis_id in [1, 2]:
            ttk.Label(axis_frame, textvariable=self.axis_data[axis_id]["ballistic"], font=("Consolas", 10)).pack(anchor=tk.W, padx=5, pady=(0, 5))

        return axis_frame

    def _create_all_axis_status_ui(self, parent):
        # Use a grid layout for up to 4 axes
        status_grid = ttk.Frame(parent)
        status_grid.columnconfigure(0, weight=1)
        status_grid.columnconfigure(1, weight=1)
        
        for i, axis_id in enumerate(SIMULATED_AXES):
            row = i // 2
            col = i % 2
            # Note: _create_single_axis_status_panel returns the inner frame now, not the LabelFrame
            panel = self._create_single_axis_status_panel(status_grid, axis_id)
            panel.grid(row=row, column=col, sticky="NSEW", padx=5, pady=5)
        
        status_grid.pack(fill=tk.BOTH, expand=True)
        return status_grid

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
            # Clear all status fields
            for axis_id in SIMULATED_AXES:
                 for key in ["pos", "spd", "vol", "cur", "cmer", "ballistic"]:
                     self.axis_data[axis_id][key].set("---")
                 # Reset indicator color
                 if self.axis_data[axis_id]["on_indicator"]:
                     self.axis_data[axis_id]["on_indicator"].config(bg='red', text='OFF')
                     
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
        """Polls status for all axes and the LRF sequentially."""
        if not self.is_connected:
            return

        is_client_ok = True
        
        # 1. Poll LRF Range
        lrf_range = self.client.request_data(protocol.NAME_TO_OPCODE["LRF_GetRange"], SYSTEM_AXIS_ID)
        if lrf_range is not None:
            self.lrf_range_var.set(f"LRF Range: {lrf_range:.2f} m")
        else:
            is_client_ok = False
            
        # 2. Poll All Axes (Position, Speed, Voltage, Current, CMER)
        for axis_id in SIMULATED_AXES:
            
            # --- Motion/Power Data (Float) ---
            pos = self.client.request_data(protocol.NAME_TO_OPCODE["MOT_GetLoadPosition"], axis_id)
            spd = self.client.request_data(protocol.NAME_TO_OPCODE["MOT_GetMotorSpeed"], axis_id)
            vol = self.client.request_data(protocol.NAME_TO_OPCODE["MOT_GetMotorVoltage"], axis_id)
            cur = self.client.request_data(protocol.NAME_TO_OPCODE["MOT_GetMotorCurrent"], axis_id)
            
            if pos is not None and spd is not None and vol is not None and cur is not None:
                self.axis_data[axis_id]["pos"].set(f"Pos: {pos:.2f}")
                self.axis_data[axis_id]["spd"].set(f"Speed: {spd:.2f}")
                self.axis_data[axis_id]["vol"].set(f"Volt: {vol:.2f} V")
                self.axis_data[axis_id]["cur"].set(f"Curr: {cur:.2f} A")
            else:
                is_client_ok = False
                break
                
            # --- Error Register (UInt16) ---
            cmer = self.client.request_data(protocol.NAME_TO_OPCODE["ERR_CaptureMotorErrorRegister"], axis_id)
            if cmer is not None:
                self.axis_data[axis_id]["cmer"].set(f"CMER: {cmer:04X}h")
                
                # Check Bit 1 for Axis ON/OFF status
                is_axis_on = (cmer & 0x0002) != 0 # Bit 1 is 0x0002
                
                if self.axis_data[axis_id]["on_indicator"]:
                    if is_axis_on:
                        self.axis_data[axis_id]["on_indicator"].config(bg='green', text='ON')
                    else:
                        self.axis_data[axis_id]["on_indicator"].config(bg='red', text='OFF')

            # --- Ballistic Offset (Float) ---
            if axis_id in [1, 2]:
                offset = self.client.request_data(protocol.NAME_TO_OPCODE["DG_GetBallisticOffset"], axis_id)
                if offset is not None:
                    self.axis_data[axis_id]["ballistic"].set(f"B.Offset: {offset:.4f}")
                else:
                    is_client_ok = False
                    break


        if not is_client_ok:
            self.toggle_connection()
            return

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

    def send_mode_control(self):
        """Sends DG_SetSyncMode (0=UNSYNC, 1=SYNC)."""
        if not self.is_connected: return
        
        # 16-bit integer for SYNC mode command
        mode_val = self.sync_mode_var.get() 
        mode_data = list(struct.pack(">H", mode_val))
        
        success = self.client.send_command(
            protocol.NAME_TO_OPCODE["DG_SetSyncMode"], SYSTEM_AXIS_ID, mode_data
        )
        if not success:
            messagebox.showerror("Error", "Failed to send DG_SetSyncMode.")
            if not self.client.sock: self.toggle_connection()
            
    def send_mode_control_inner(self):
        """Sends DG_SetInnerMode (0=OUTER, 1=INNER)."""
        if not self.is_connected or self.sync_mode_var.get() == 1: return # Ignore if in Sync mode
        
        # 16-bit integer for INNER mode command
        mode_val = self.inner_mode_var.get() 
        mode_data = list(struct.pack(">H", mode_val))
        
        success = self.client.send_command(
            protocol.NAME_TO_OPCODE["DG_SetInnerMode"], SYSTEM_AXIS_ID, mode_data
        )
        if not success:
            messagebox.showerror("Error", "Failed to send DG_SetInnerMode.")
            if not self.client.sock: self.toggle_connection()
            
    def send_axis_command(self, command_name):
        """Sends a single command (Axis ON/OFF/RESET)."""
        if not self.is_connected:
            messagebox.showwarning("Warning", "Not connected.")
            return

        try:
            axis_id = int(self.target_axis_var.get())
            opcode = protocol.NAME_TO_OPCODE[command_name]
        except ValueError:
            messagebox.showerror("Error", "Please select a valid Target Axis ID.")
            return
        except KeyError:
            messagebox.showerror("Error", f"Unknown command: {command_name}")
            return
            
        success = self.client.send_command(opcode, axis_id)
        
        if not success:
            messagebox.showerror("Error", f"Failed to send {command_name} command.")
            if not self.client.sock: self.toggle_connection()
        else:
            print(f"[Client] {command_name} sent successfully for Axis {axis_id}.")

    def send_move_command(self, move_opcode):
        if not self.is_connected:
            messagebox.showwarning("Warning", "Not connected.")
            return
        
        try:
            target_pos = float(self.target_pos_var.get())
            speed = float(self.speed_cmd_var.get())
            accel = float(self.accel_cmd_var.get())
            axis_id = int(self.target_axis_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid input. Please enter numbers.")
            return
            
        success = True
        
        # Command Sequence: SetMode -> SetAccel -> SetSpeed -> SetPos -> Update
        
        # 1. Set Position Mode (Simple ACK command)
        if not self.client.send_command(protocol.NAME_TO_OPCODE["MOT_SetPositionMode"], axis_id):
            success = False
            
        # 2. Set Acceleration
        if success:
            accel_data = list(struct.pack(">f", accel))
            if not self.client.send_command(protocol.NAME_TO_OPCODE["MOT_SetAcceleration"], axis_id, accel_data):
                success = False

        # 3. Set Speed
        if success:
            speed_data = list(struct.pack(">f", speed))
            if not self.client.send_command(protocol.NAME_TO_OPCODE["MOT_SetSpeed"], axis_id, speed_data):
                success = False
        
        # 4. Set Position
        if success:
            pos_data = list(struct.pack(">f", target_pos))
            if not self.client.send_command(move_opcode, axis_id, pos_data):
                success = False

        # 5. Update (start motion)
        if success:
            if not self.client.send_command(protocol.NAME_TO_OPCODE["MOT_Update"], axis_id):
                success = False

        if not success:
            messagebox.showerror("Error", "Failed to send command sequence. Check connection.")
            if not self.client.sock: self.toggle_connection()
        else:
            print(f"[Client] Move sequence sent successfully for Axis {axis_id}.")
            
    def send_abs_move(self):
        self.send_move_command(protocol.NAME_TO_OPCODE["MOT_SetPositionAbsolute"])
        
    def send_rel_move(self):
        self.send_move_command(protocol.NAME_TO_OPCODE["MOT_SetPositionRelative"])
        
    def send_ballistic_offset(self):
        if not self.is_connected:
            messagebox.showwarning("Warning", "Not connected.")
            return
        
        try:
            offset = float(self.ballistic_offset_var.get())
            axis_id = int(self.target_axis_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid offset. Please enter a number.")
            return
        
        if axis_id not in [1, 2]:
            messagebox.showwarning("Warning", f"Ballistic Offset only supported for Axis 1 and 2. Ignoring command for Axis {axis_id}.")
            return
            
        offset_data = list(struct.pack(">f", offset))
        success = self.client.send_command(
            protocol.NAME_TO_OPCODE["DG_SetBallisticOffset"], axis_id, offset_data
        )
        
        if not success:
            messagebox.showerror("Error", "Failed to send DG_SetBallisticOffset command.")
            if not self.client.sock: self.toggle_connection()
        else:
            print(f"[Client] Ballistic Offset set successfully for Axis {axis_id}.")

    def on_closing(self):
        self.stop_polling()
        self.client.disconnect()
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
