import socket
import threading
import time
import re

# ===============================
# Server Configuration
# ===============================
HOST = '0.0.0.0'  # Listen on all interfaces (covers 132.8.7.121 if local)
PORT = 8080       # Port extracted from PCAP Host header
BUFFER_SIZE = 4096

class OnvifSimulator:
    def __init__(self):
        self.is_running = True

    def start(self):
        """Starts the TCP Server."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((HOST, PORT))
                s.listen(5)
                print(f"[ONVIF Sim] Listening on {HOST}:{PORT} (TCP)...")
                
                while self.is_running:
                    try:
                        conn, addr = s.accept()
                        client_thread = threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True)
                        client_thread.start()
                    except KeyboardInterrupt:
                        break
            except Exception as e:
                print(f"[ONVIF Sim] Critical Server Error: {e}")

    def handle_client(self, conn, addr):
        print(f"[ONVIF Sim] Connection from {addr}")
        try:
            while True:
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    break
                
                # Decode to string for analysis (ignore non-ascii garbage if present)
                request_text = data.decode('utf-8', errors='ignore')
                
                # --- 1. Handle "Expect: 100-continue" ---
                # The PCAP shows the client expects a specific handshake before sending the body.
                if "Expect: 100-continue" in request_text:
                    # print(f"[ONVIF Sim] Sending 100 Continue to {addr}")
                    conn.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
                    # We don't break/return here; we wait for the subsequent body packet
                    continue

                # --- 2. Identify Command Action ---
                # We look for specific SOAP Actions in the header or body
                
                if "GetStatus" in request_text:
                    self.send_get_status_response(conn)
                
                elif "AbsoluteMove" in request_text:
                    self.send_absolute_move_response(conn)

                elif "Stop" in request_text:
                    self.send_stop_response(conn)
                
                # Detect standard HTTP GET (often used for WSDL discovery, ignored here)
                elif request_text.startswith("GET "):
                    pass 

        except ConnectionResetError:
            print(f"[ONVIF Sim] Client {addr} disconnected abruptly.")
        except Exception as e:
            print(f"[ONVIF Sim] Error handling client {addr}: {e}")
        finally:
            conn.close()

    # ===============================
    # Response Generators
    # ===============================

    def send_get_status_response(self, conn):
        print("[ONVIF Sim] Action: GetStatus -> sending PTZStatus")
        
        # Extracted from your PCAP "GetStatusResponse"
        body = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
    <SOAP-ENV:Header/>
    <SOAP-ENV:Body>
        <tptz:GetStatusResponse>
            <tptz:PTZStatus>
                <tt:Position>
                    <tt:PanTilt x="0" y="0" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace"></tt:PanTilt>
                    <tt:Zoom x="0" space="http://www.onvif.org/ver10/tptz/ZoomSpaces/PositionGenericSpace"></tt:Zoom>
                </tt:Position>
                <tt:MoveStatus>
                    <tt:PanTilt>IDLE</tt:PanTilt>
                    <tt:Zoom>IDLE</tt:Zoom>
                </tt:MoveStatus>
                <tt:UtcTime>2023-03-02T16:02:29Z</tt:UtcTime>
            </tptz:PTZStatus>
        </tptz:GetStatusResponse>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        
        self.send_http_soap(conn, body, action="http://www.onvif.org/ver20/ptz/wsdl/GetStatus")

    def send_absolute_move_response(self, conn):
        print("[ONVIF Sim] Action: AbsoluteMove -> sending OK")
        
        # AbsoluteMove usually returns an empty body or simple Response tag
        body = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">
    <SOAP-ENV:Header/>
    <SOAP-ENV:Body>
        <tptz:AbsoluteMoveResponse></tptz:AbsoluteMoveResponse>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        
        self.send_http_soap(conn, body, action="http://www.onvif.org/ver20/ptz/wsdl/AbsoluteMove")

    def send_stop_response(self, conn):
        print("[ONVIF Sim] Action: Stop -> sending OK")
        
        body = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">
    <SOAP-ENV:Header/>
    <SOAP-ENV:Body>
        <tptz:StopResponse></tptz:StopResponse>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        
        self.send_http_soap(conn, body, action="http://www.onvif.org/ver20/ptz/wsdl/Stop")

    def send_http_soap(self, conn, xml_body, action):
        """Wraps XML in HTTP headers."""
        xml_bytes = xml_body.encode('utf-8')
        length = len(xml_bytes)
        
        # Headers based on your PCAP
        response = (
            f"HTTP/1.1 200 OK\r\n"
            f"Server: gSOAP/2.8\r\n"
            f"Content-Type: application/soap+xml; charset=utf-8; action=\"{action}\"\r\n"
            f"Content-Length: {length}\r\n"
            f"Connection: keep-alive\r\n" # Keep connection open for replay
            f"\r\n"
        ).encode('utf-8') + xml_bytes
        
        conn.sendall(response)

if __name__ == "__main__":
    sim = OnvifSimulator()
    sim.start()