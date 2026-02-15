import socket
import threading
import time
import random

# ===============================
# Server Configuration
# ===============================
HOST = '127.0.0.1'  # Listens on all interfaces (binds 132.8.7.121 if IP alias exists)
PORT = 8080       # Port from PCAP Host header
BUFFER_SIZE = 4096

class OnvifSimulator:
    def __init__(self):
        self.is_running = True
        self.lrf_distance = 2950.0  # Default simulated distance in dm

    def start(self):
        """Starts the TCP Server."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((HOST, PORT))
                s.listen(5)
                print(f"[ONVIF Sim] Listening on {HOST}:{PORT} (TCP)...")
                print(f"[ONVIF Sim] Supports: PTZ (GetStatus, Move, Stop) and LRF (MakeMeasurement)")
                
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
        # print(f"[ONVIF Sim] Connection from {addr}")
        try:
            while True:
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    break
                
                request_text = data.decode('utf-8', errors='ignore')
                
                # --- 1. Handle "Expect: 100-continue" ---
                if "Expect: 100-continue" in request_text:
                    conn.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
                    continue

                # --- 2. Identify Command Action ---
                
                # >>>> LRF COMMANDS <<<<
                if "LRFMakeMeasurement" in request_text:
                    self.send_lrf_response(conn)

                # >>>> PTZ COMMANDS <<<<
                elif "GetStatus" in request_text:
                    self.send_get_status_response(conn)
                
                elif "AbsoluteMove" in request_text:
                    self.send_absolute_move_response(conn)

                elif "Stop" in request_text:
                    self.send_stop_response(conn)
                
                elif request_text.startswith("GET "):
                    # Simple handling for browser/discovery
                    conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")

        except ConnectionResetError:
            pass # Client disconnected
        except Exception as e:
            print(f"[ONVIF Sim] Error handling client {addr}: {e}")
        finally:
            conn.close()

    # ===============================
    # Response Generators
    # ===============================

    def send_lrf_response(self, conn):
        # Simulate small fluctuation in distance
        val = self.lrf_distance + random.choice([0, 1.0, -1.0])
        print(f"[ONVIF Sim] Action: LRFMakeMeasurement -> {val} dm")

        # Constructed based on "example for onvif lrf pcap"
        body = f"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:SOAP-ENC="http://www.w3.org/2003/05/soap-encoding" xmlns:sdcs="http://www.seraphim-opt.com/SdcsCustom">
    <SOAP-ENV:Header/>
    <SOAP-ENV:Body>
        <sdcs:LRFMakeMeasurementResponse>
            <RangeMode>standard single measurement</RangeMode>
            <Measurement>{val:.6f}</Measurement>
            <Units>dm</Units>
        </sdcs:LRFMakeMeasurementResponse>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        
        self.send_http_soap(conn, body, action="http://www.seraphim-opt.com/SdcsCustom/LRFMakeMeasurement")

    def send_get_status_response(self, conn):
        # Standard ONVIF PTZ Status
        # print("[ONVIF Sim] Action: GetStatus")
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
        print("[ONVIF Sim] Action: AbsoluteMove")
        body = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">
    <SOAP-ENV:Header/>
    <SOAP-ENV:Body>
        <tptz:AbsoluteMoveResponse></tptz:AbsoluteMoveResponse>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        self.send_http_soap(conn, body, action="http://www.onvif.org/ver20/ptz/wsdl/AbsoluteMove")

    def send_stop_response(self, conn):
        print("[ONVIF Sim] Action: Stop")
        body = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">
    <SOAP-ENV:Header/>
    <SOAP-ENV:Body>
        <tptz:StopResponse></tptz:StopResponse>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        self.send_http_soap(conn, body, action="http://www.onvif.org/ver20/ptz/wsdl/Stop")

    def send_http_soap(self, conn, xml_body, action):
        xml_bytes = xml_body.encode('utf-8')
        length = len(xml_bytes)
        
        response = (
            f"HTTP/1.1 200 OK\r\n"
            f"Server: gSOAP/2.8\r\n"
            f"Content-Type: application/soap+xml; charset=utf-8; action=\"{action}\"\r\n"
            f"Content-Length: {length}\r\n"
            f"Connection: keep-alive\r\n"
            f"\r\n"
        ).encode('utf-8') + xml_bytes
        
        conn.sendall(response)

if __name__ == "__main__":
    sim = OnvifSimulator()
    sim.start()