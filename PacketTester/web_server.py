#!/usr/bin/env python3
"""
Web Server for PacketTester
Provides REST API to execute packet replay operations
"""
import os
import subprocess
import sys
import threading
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

try:
    import netifaces
except Exception:
    netifaces = None

ROOT = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder='web', static_url_path='')
CORS(app)

# Global process tracker
current_process = None
process_lock = threading.Lock()

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
    files = [f for f in os.listdir(pcap_dir) if f.endswith(('.pcap', '.pcapng'))]
    return files

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('web', 'index.html')

@app.route('/api/interfaces', methods=['GET'])
def get_interfaces():
    """Get available network interfaces"""
    try:
        interfaces = list_interfaces()
        return jsonify({"success": True, "data": interfaces})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/pcaps', methods=['GET'])
def get_pcaps():
    """Get available PCAP files"""
    try:
        pcaps = list_pcaps()
        return jsonify({"success": True, "data": pcaps})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/replay', methods=['POST'])
def start_replay():
    """Start packet replay"""
    global current_process
    
    with process_lock:
        if current_process and current_process.poll() is None:
            return jsonify({"success": False, "error": "Replay already running"}), 400
        
        data = request.json
        interface = data.get('interface')
        pcap = data.get('pcap')
        pps = data.get('pps', 0)
        loop = data.get('loop', 1)
        
        if not interface or not pcap:
            return jsonify({"success": False, "error": "Missing interface or pcap"}), 400
        
        # Build pcap path
        if not os.path.isabs(pcap):
            pcap_path = os.path.join(ROOT, "pcaps", pcap)
        else:
            pcap_path = pcap
        
        if not os.path.exists(pcap_path):
            return jsonify({"success": False, "error": f"PCAP file not found: {pcap}"}), 404
        
        # Use venv python if available, otherwise system python
        venv_py = os.path.join(ROOT, ".venv", "bin", "python")
        exe = venv_py if os.path.exists(venv_py) else sys.executable
        script = os.path.join(ROOT, "packet_blaster.py")
        
        args = [
            exe, script,
            "--pcap-in", pcap_path,
            "--interface", interface,
            "--pps", str(pps),
            "--loop", str(loop)
        ]
        
        try:
            # Start the process in background
            current_process = subprocess.Popen(
                args,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            # Start a thread to read output
            def read_output():
                if current_process:
                    for line in current_process.stdout:
                        print(line, end='')  # Print to console for now
                    current_process.wait()
            
            threading.Thread(target=read_output, daemon=True).start()
            
            return jsonify({
                "success": True,
                "message": "Replay started",
                "command": " ".join(args)
            })
        
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/stop', methods=['POST'])
def stop_replay():
    """Stop current replay"""
    global current_process
    
    with process_lock:
        if not current_process or current_process.poll() is not None:
            return jsonify({"success": False, "error": "No replay running"}), 400
        
        try:
            current_process.terminate()
            current_process.wait(timeout=5)
            current_process = None
            return jsonify({"success": True, "message": "Replay stopped"})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current replay status"""
    global current_process
    
    with process_lock:
        is_running = current_process is not None and current_process.poll() is None
        return jsonify({
            "success": True,
            "data": {
                "running": is_running
            }
        })

if __name__ == "__main__":
    # Create web directory if it doesn't exist
    web_dir = os.path.join(ROOT, "web")
    os.makedirs(web_dir, exist_ok=True)
    
    print("=" * 60)
    print("PacketTester Web Server")
    print("=" * 60)
    print(f"Server running at: http://localhost:5001")
    print(f"PCAP directory: {os.path.join(ROOT, 'pcaps')}")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5001, debug=True)

