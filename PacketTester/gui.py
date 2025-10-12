#!/usr/bin/env python3
"""
PacketTester GUI - PCAP Replay Tool
Beautiful desktop interface for replaying PCAP files with original packet structure preserved.
"""
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

try:
    import netifaces
except Exception:
    netifaces = None

ROOT = os.path.dirname(os.path.abspath(__file__))

def list_interfaces():
    """Get list of network interfaces"""
    if netifaces is None:
        return ["en0", "lo0", "eth0"]
    return list(netifaces.interfaces())

def list_pcaps():
    """Get list of available PCAP files"""
    pcap_dir = os.path.join(ROOT, "pcaps")
    if not os.path.exists(pcap_dir):
        return []
    return [f for f in os.listdir(pcap_dir) if f.endswith(('.pcap', '.pcapng'))]

class PacketTesterGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PacketTester")
        self.geometry("1000x850")
        self.resizable(False, False)  # Fixed size
        self.configure(bg="#f5f5f5")

        # ---- Styling / Theme ----
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass
        
        # Custom styles
        self.style.configure("TLabel", font=("Helvetica", 11), background="#f5f5f5")
        self.style.configure("TButton", font=("Helvetica", 11), padding=6)
        self.style.configure("TEntry", font=("Helvetica", 11), padding=4)
        self.style.configure("TCombobox", font=("Helvetica", 11), padding=4)
        
        # Green Fire button
        self.style.configure("Green.TButton", font=("Helvetica", 13, "bold"), padding=12, 
                            foreground="#ffffff", background="#10b981", relief=tk.FLAT)
        self.style.map("Green.TButton", 
                      background=[("active", "#059669"), ("disabled", "#86efac")],
                      relief=[("pressed", tk.SUNKEN)])
        
        # Red Stop button
        self.style.configure("Red.TButton", font=("Helvetica", 13, "bold"), padding=12,
                            foreground="#ffffff", background="#ef4444", relief=tk.FLAT)
        self.style.map("Red.TButton", 
                      background=[("active", "#dc2626")],
                      relief=[("pressed", tk.SUNKEN)])
        
        self.style.configure("Header.TLabel", font=("Helvetica", 24, "bold"), background="#f5f5f5", foreground="#1f2937")
        self.style.configure("Subheader.TLabel", font=("Helvetica", 11), foreground="#6b7280", background="#f5f5f5")
        self.style.configure("Card.TLabelframe", padding=16, background="#ffffff", relief=tk.SOLID, borderwidth=1)
        self.style.configure("Card.TLabelframe.Label", font=("Helvetica", 12, "bold"), background="#ffffff", foreground="#374151")
        
        # Variables
        self.interface_var = tk.StringVar(value=list_interfaces()[0] if list_interfaces() else "en0")
        self.pcap_var = tk.StringVar()
        self.loop_var = tk.IntVar(value=1)
        self.pps_var = tk.IntVar(value=1000)

        self._build_widgets()
        self._proc = None

    def _build_widgets(self):
        # Main container
        container = tk.Frame(self, bg="#f5f5f5", padx=20, pady=20)
        container.pack(fill=tk.BOTH, expand=True)

        # Header with action buttons
        header_frame = tk.Frame(container, bg="#f5f5f5")
        header_frame.pack(fill=tk.X, pady=(0, 16))
        
        # Title on left
        title_frame = tk.Frame(header_frame, bg="#f5f5f5")
        title_frame.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(title_frame, text="PacketTester", style="Header.TLabel").pack(anchor="w")
        ttk.Label(title_frame, text="PCAP Replay Tool", style="Subheader.TLabel").pack(anchor="w")
        
        # Action buttons on right
        btn_frame = tk.Frame(header_frame, bg="#f5f5f5")
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(20,0))
        
        self.run_btn = ttk.Button(btn_frame, text="➨ Fire", command=self._on_run, style="Green.TButton", width=12)
        self.run_btn.pack(side=tk.TOP, pady=(0,8))
        
        self.stop_btn = ttk.Button(btn_frame, text="⏹ Stop", command=self._on_stop, style="Red.TButton", width=12)
        self.stop_btn.pack(side=tk.TOP)

        # Main settings card
        main_card = ttk.Labelframe(container, text="Configuration", style="Card.TLabelframe")
        main_card.pack(fill=tk.X, pady=(0, 12))

        # Interface
        row = 0
        ttk.Label(main_card, text="Interface").grid(row=row, column=0, sticky="w", padx=(0,12), pady=6)
        ttk.Combobox(main_card, textvariable=self.interface_var, values=list_interfaces(), 
                     state="readonly", width=20).grid(row=row, column=1, sticky="w", pady=6)

        # PCAP selection
        row += 1
        ttk.Label(main_card, text="PCAP File").grid(row=row, column=0, sticky="w", padx=(0,12), pady=6)
        pcap_frame = tk.Frame(main_card, bg="#ffffff")
        pcap_frame.grid(row=row, column=1, columnspan=3, sticky="ew", pady=6)
        ttk.Combobox(pcap_frame, textvariable=self.pcap_var, values=list_pcaps(), 
                     width=30).pack(side=tk.LEFT, padx=(0,8))
        ttk.Button(pcap_frame, text="Browse...", command=self._choose_pcap).pack(side=tk.LEFT)

        # Replay options card
        replay_card = ttk.Labelframe(container, text="Replay Options", style="Card.TLabelframe")
        replay_card.pack(fill=tk.X, pady=(0, 12))

        row = 0
        ttk.Label(replay_card, text="Loop Count").grid(row=row, column=0, sticky="w", padx=(0,12), pady=6)
        ttk.Spinbox(replay_card, from_=1, to=1000, textvariable=self.loop_var, width=12).grid(row=row, column=1, sticky="w", pady=6)
        
        row += 1
        ttk.Label(replay_card, text="PPS (Packets/sec)").grid(row=row, column=0, sticky="w", padx=(0,12), pady=6)
        ttk.Entry(replay_card, textvariable=self.pps_var, width=12).grid(row=row, column=1, sticky="w", pady=6)
        ttk.Label(replay_card, text="(0 = original timing)", font=("Helvetica", 9), foreground="#6b7280").grid(row=row, column=2, sticky="w", padx=(8,0), pady=6)

        # Output section
        output_frame = tk.Frame(container, bg="#f5f5f5")
        output_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 8))
        ttk.Label(output_frame, text="Output", font=("SF Pro Text", 12, "bold")).pack(anchor="w", pady=(0,8))
        self.output = scrolledtext.ScrolledText(output_frame, height=14, font=("SF Mono", 10), 
                                                 bg="#1e1e1e", fg="#d4d4d4", insertbackground="#ffffff",
                                                 wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        self.output.pack(fill=tk.BOTH, expand=True)

        # Clear output button at bottom
        clear_frame = tk.Frame(container, bg="#f5f5f5")
        clear_frame.pack(fill=tk.X, pady=(8,0))
        ttk.Button(clear_frame, text="Clear Output", command=lambda: self.output.delete(1.0, tk.END), width=15).pack(side=tk.LEFT)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Frame(self, bg="#374151", height=32)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        status_label = tk.Label(status_bar, textvariable=self.status_var, background="#374151", 
                               foreground="#ffffff", font=("Helvetica", 10), anchor="w")
        status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=16, pady=8)

    def _choose_pcap(self):
        pcap_dir = os.path.join(ROOT, "pcaps")
        path = filedialog.askopenfilename(
            initialdir=pcap_dir if os.path.exists(pcap_dir) else ROOT,
            filetypes=[("PCAP Files", "*.pcap *.pcapng"), ("All Files", "*.*")]
        )
        if path:
            # Store just the filename if it's in the pcaps directory
            if path.startswith(pcap_dir):
                self.pcap_var.set(os.path.basename(path))
            else:
                self.pcap_var.set(path)

    def _append_output(self, text: str):
        self.output.insert(tk.END, text)
        self.output.see(tk.END)
        self.output.update_idletasks()

    def _run_in_thread(self, args):
        def target():
            try:
                cmd_str = " ".join(args)
                self._append_output("=" * 60 + "\n")
                self._append_output("▶ Running command:\n")
                self._append_output(cmd_str + "\n")
                self._append_output("=" * 60 + "\n\n")
                self.status_var.set("Running...")
                self.run_btn.state(["disabled"])
                
                self._proc = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, 
                                               stderr=subprocess.STDOUT, text=True)
                for line in self._proc.stdout:
                    self._append_output(line)
                
                self._proc.wait()
                self._append_output("\n✓ Complete\n")
                self.status_var.set("Ready")
            except Exception as ex:
                self._append_output(f"\n✗ Error: {ex}\n")
                messagebox.showerror("Error", str(ex))
                self.status_var.set("Error")
            finally:
                self._proc = None
                self.run_btn.state(["!disabled"])
        
        threading.Thread(target=target, daemon=True).start()

    def _on_run(self):
        # Use venv python if available
        venv_py = os.path.join(ROOT, ".venv", "bin", "python")
        exe = venv_py if os.path.exists(venv_py) else sys.executable
        script = os.path.join(ROOT, "packet_blaster.py")
        
        pcap = self.pcap_var.get()
        if not pcap:
            messagebox.showwarning("Missing PCAP", "Please select a PCAP file")
            return
        
        # If just filename, prepend pcaps directory
        if not os.path.isabs(pcap) and not os.path.exists(pcap):
            pcap = os.path.join(ROOT, "pcaps", pcap)
        
        if not os.path.exists(pcap):
            messagebox.showerror("File Not Found", f"PCAP file not found: {pcap}")
            return
        
        args = [exe, script,
                "--pcap-in", pcap,
                "--interface", self.interface_var.get(), 
                "--pps", str(self.pps_var.get()),
                "--loop", str(self.loop_var.get())]

        self._run_in_thread(args)

    def _on_stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._append_output("\n⏹ Process terminated\n")
            self.status_var.set("Stopped")

if __name__ == "__main__":
    app = PacketTesterGUI()
    app.mainloop()
