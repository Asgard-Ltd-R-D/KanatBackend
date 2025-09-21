#!/usr/bin/env python3
"""
ONVIF Packet Blaster

Fires TCP packets with proper ONVIF/SOAP XML format at specified rate.
The packets match the expected parser format for OnVIFPacketEntity.

Usage:
    python onvif_blaster.py --host 192.168.1.100 --port 8080 --pps 100 --seconds 10
    python onvif_blaster.py --host 192.168.1.100 --port 8080 --pps 500 --seconds 30 --profile DAY --type CMD
"""

import argparse
import socket
import time
import struct
import random
import uuid
import threading
import http.server
import socketserver
from typing import List, Tuple


class OnVIFMockHTTPServer(http.server.BaseHTTPRequestHandler):
    """Mock HTTP server that accepts ONVIF requests and generates responses"""
    
    def do_POST(self):
        """Handle POST requests (ONVIF commands)"""
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        # Log the request
        print(f"Received ONVIF POST request to {self.path}")
        print(f"Content-Length: {content_length}")
        print(f"Headers: {dict(self.headers)}")
        
        # Generate a mock response
        response_xml = self._generate_mock_response(post_data)
        
        # Send response
        self.send_response(200)
        self.send_header('Content-Type', 'text/xml; charset=utf-8')
        self.send_header('Content-Length', str(len(response_xml.encode('utf-8'))))
        self.send_header('Server', 'ONVIF Mock Device')
        self.end_headers()
        self.wfile.write(response_xml.encode('utf-8'))
    
    def _generate_mock_response(self, request_data: bytes) -> str:
        """Generate a mock ONVIF response based on the request"""
        request_str = request_data.decode('utf-8', errors='ignore')
        
        # Simple response generation
        message_id = str(uuid.uuid4())
        
        if 'GetStatus' in request_str:
            # PTZ status response
            zoom_value = random.uniform(0.0, 1.0)
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" 
            xmlns:a="http://www.w3.org/2005/08/addressing"
            xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl"
            xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Header>
    <a:MessageID>urn:uuid:{message_id}</a:MessageID>
    <a:Action>http://www.onvif.org/ver20/ptz/wsdl/GetStatusResponse</a:Action>
  </s:Header>
  <s:Body>
    <tptz:GetStatusResponse>
      <tptz:PTZStatus>
        <tt:Position>
          <tt:Pan x="0.0" y="0.0" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace"/>
          <tt:Tilt x="0.0" y="0.0" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace"/>
          <tt:Zoom x="{zoom_value:.3f}" space="http://www.onvif.org/ver10/tptz/ZoomSpaces/PositionGenericSpace"/>
        </tt:Position>
        <tt:MoveStatus>
          <tt:PanTilt>IDLE</tt:PanTilt>
          <tt:Zoom>IDLE</tt:Zoom>
        </tt:MoveStatus>
      </tptz:PTZStatus>
    </tptz:GetStatusResponse>
  </s:Body>
</s:Envelope>"""
        elif 'GetPower' in request_str:
            # LRF power response
            measurement_value = random.uniform(100.0, 2000.0)
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" 
                   xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
                   xmlns:sdcs="urn:schemas-xmlsoap-org:sdcs">
  <SOAP-ENV:Header>
    <wsa:MessageID>urn:uuid:{message_id}</wsa:MessageID>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2004/08/addressing/action</wsa:Action>
  </SOAP-ENV:Header>
  <SOAP-ENV:Body>
    <sdcs:LRFMakeMeasurementResponse>
      <sdcs:Measurement>{measurement_value:.3f}</sdcs:Measurement>
      <sdcs:Status>OK</sdcs:Status>
    </sdcs:LRFMakeMeasurementResponse>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        else:
            # Generic response
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Header>
    <a:MessageID>urn:uuid:{message_id}</a:MessageID>
  </s:Header>
  <s:Body>
    <s:Fault>
      <faultcode>s:Client</faultcode>
      <faultstring>Unknown request</faultstring>
    </s:Fault>
  </s:Body>
</s:Envelope>"""
    
    def log_message(self, format, *args):
        """Override to reduce log noise"""
        pass


def start_mock_server(host: str, port: int) -> threading.Thread:
    """Start the mock HTTP server in a separate thread"""
    def run_server():
        with socketserver.TCPServer((host, port), OnVIFMockHTTPServer) as httpd:
            print(f"Mock ONVIF HTTP server started on {host}:{port}")
            print("Server is ready to receive ONVIF requests...")
            httpd.serve_forever()
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    return server_thread


class OnVIFPacketBuilder:
    """Builds ONVIF packets with proper SOAP/XML format for the parser"""
    
    # Profile types and their corresponding operations
    PROFILES = {
        "DAY": {
            "CMD": "tptz:GetStatus",
            "RPT": "tptz:GetStatusResponse"
        },
        "IR": {
            "CMD": "tptz:GetStatus", 
            "RPT": "tptz:GetStatusResponse"
        },
        "LRF": {
            "CMD": "sdcs:GetPower",
            "RPT": "sdcs:LRFMakeMeasurementResponse"
        }
    }
    
    def __init__(self, target_ip: str, target_port: int, source_ip: str = "192.168.1.102", source_port: int = 12346):
        self.target_ip = target_ip
        self.target_port = target_port
        self.source_ip = source_ip
        self.source_port = source_port
    
    def build_packet(self, profile: str = "DAY", packet_type: str = "CMD", 
                    zoom_value: float = None, measurement_value: float = None,
                    message_id: str = None) -> bytes:
        """
        Builds a complete Ethernet frame with ONVIF/SOAP XML for raw socket transmission.
        This matches what the OnVIFPacketParser expects.
        
        Args:
            profile: Profile type (DAY, IR, LRF)
            packet_type: CMD (command) or RPT (response)
            zoom_value: Zoom value for DAY/IR responses
            measurement_value: Measurement value for LRF responses
            message_id: Message ID for correlation (auto-generated if None)
        
        Returns complete Ethernet frame
        """
        if message_id is None:
            message_id = str(uuid.uuid4())
        
        if profile not in self.PROFILES:
            profile = "DAY"
        
        # Generate XML content based on profile and type
        if packet_type == "CMD":
            xml_content = self._build_cmd_xml(profile, message_id)
        else:  # RPT
            xml_content = self._build_rpt_xml(profile, message_id, zoom_value, measurement_value)
        
        # Build HTTP request/response
        if packet_type == "CMD":
            http_content = self._build_http_request(xml_content)
        else:
            http_content = self._build_http_response(xml_content)
        
        # Build complete Ethernet frame
        return self._build_ethernet_frame(http_content)
    
    def _build_cmd_xml(self, profile: str, message_id: str) -> str:
        """Build SOAP XML for command packets"""
        if profile == "LRF":
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" 
                   xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
                   xmlns:sdcs="urn:schemas-xmlsoap-org:sdcs">
  <SOAP-ENV:Header>
    <wsa:MessageID>urn:uuid:{message_id}</wsa:MessageID>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2004/08/addressing/action</wsa:Action>
  </SOAP-ENV:Header>
  <SOAP-ENV:Body>
    <sdcs:GetPower>
      <sdcs:Power>ON</sdcs:Power>
    </sdcs:GetPower>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        else:  # DAY or IR
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" 
            xmlns:a="http://www.w3.org/2005/08/addressing"
            xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">
  <s:Header>
    <a:MessageID>urn:uuid:{message_id}</a:MessageID>
    <a:Action>http://www.onvif.org/ver20/ptz/wsdl/GetStatus</a:Action>
  </s:Header>
  <s:Body>
    <tptz:GetStatus>
      <tptz:ProfileToken>{profile.lower()}</tptz:ProfileToken>
    </tptz:GetStatus>
  </s:Body>
</s:Envelope>"""
    
    def _build_rpt_xml(self, profile: str, message_id: str, zoom_value: float = None, measurement_value: float = None) -> str:
        """Build SOAP XML for response packets"""
        if profile == "LRF":
            if measurement_value is None:
                measurement_value = random.uniform(100.0, 2000.0)
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" 
                   xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
                   xmlns:sdcs="urn:schemas-xmlsoap-org:sdcs">
  <SOAP-ENV:Header>
    <wsa:MessageID>urn:uuid:{message_id}</wsa:MessageID>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2004/08/addressing/action</wsa:Action>
  </SOAP-ENV:Header>
  <SOAP-ENV:Body>
    <sdcs:LRFMakeMeasurementResponse>
      <sdcs:Measurement>{measurement_value:.3f}</sdcs:Measurement>
      <sdcs:Status>OK</sdcs:Status>
    </sdcs:LRFMakeMeasurementResponse>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
        else:  # DAY or IR
            if zoom_value is None:
                zoom_value = random.uniform(0.0, 1.0)
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" 
            xmlns:a="http://www.w3.org/2005/08/addressing"
            xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl"
            xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Header>
    <a:MessageID>urn:uuid:{message_id}</a:MessageID>
    <a:Action>http://www.onvif.org/ver20/ptz/wsdl/GetStatusResponse</a:Action>
  </s:Header>
  <s:Body>
    <tptz:GetStatusResponse>
      <tptz:PTZStatus>
        <tt:Position>
          <tt:Pan x="0.0" y="0.0" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace"/>
          <tt:Tilt x="0.0" y="0.0" space="http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace"/>
          <tt:Zoom x="{zoom_value:.3f}" space="http://www.onvif.org/ver10/tptz/ZoomSpaces/PositionGenericSpace"/>
        </tt:Position>
        <tt:MoveStatus>
          <tt:PanTilt>IDLE</tt:PanTilt>
          <tt:Zoom>IDLE</tt:Zoom>
        </tt:MoveStatus>
      </tptz:PTZStatus>
    </tptz:GetStatusResponse>
  </s:Body>
</s:Envelope>"""
    
    def _build_http_request(self, xml_content: str) -> bytes:
        """Build HTTP request with SOAP XML"""
        http_request = f"""POST /onvif/device_service HTTP/1.1\r
Host: {self.target_ip}:{self.target_port}\r
Content-Type: text/xml; charset=utf-8\r
Content-Length: {len(xml_content.encode('utf-8'))}\r
SOAPAction: "http://www.onvif.org/ver20/ptz/wsdl/GetStatus"\r
User-Agent: ONVIF Client\r
Connection: keep-alive\r
\r
{xml_content}"""
        return http_request.encode('utf-8')
    
    def _build_http_response(self, xml_content: str) -> bytes:
        """Build HTTP response with SOAP XML"""
        http_response = f"""HTTP/1.1 200 OK\r
Content-Type: text/xml; charset=utf-8\r
Content-Length: {len(xml_content.encode('utf-8'))}\r
Server: ONVIF Device\r
Connection: keep-alive\r
\r
{xml_content}"""
        return http_response.encode('utf-8')
    
    def _build_ethernet_frame(self, http_content: bytes) -> bytes:
        """Builds complete Ethernet frame with IP and TCP headers"""
        # Ethernet header (14 bytes)
        dst_mac = b'\xff\xff\xff\xff\xff\xff'  # Broadcast MAC
        src_mac = b'\x00\x11\x22\x33\x44\x66'  # Fake source MAC
        eth_type = b'\x08\x00'  # IPv4 (0x0800)
        eth_header = dst_mac + src_mac + eth_type
        
        # IPv4 header (20 bytes)
        version_ihl = 0x45  # Version 4, IHL 5 (20 bytes)
        tos = 0x00  # Type of Service
        total_length = 20 + 20 + len(http_content)  # IP header + TCP header + HTTP content
        identification = random.randint(0, 65535)
        flags_fragment = 0x4000  # Don't fragment
        ttl = 64
        protocol = 6  # TCP
        checksum = 0  # Will calculate
        src_ip = self._ip_to_bytes(self.source_ip)
        dst_ip = self._ip_to_bytes(self.target_ip)
        
        # Build IP header
        ip_header = bytearray(20)
        struct.pack_into('>B', ip_header, 0, version_ihl)
        struct.pack_into('>B', ip_header, 1, tos)
        struct.pack_into('>H', ip_header, 2, total_length)
        struct.pack_into('>H', ip_header, 4, identification)
        struct.pack_into('>H', ip_header, 6, flags_fragment)
        struct.pack_into('>B', ip_header, 8, ttl)
        struct.pack_into('>B', ip_header, 9, protocol)
        struct.pack_into('>H', ip_header, 10, checksum)
        ip_header[12:16] = src_ip
        ip_header[16:20] = dst_ip
        
        # Calculate IP checksum
        ip_checksum = self._calculate_checksum(ip_header)
        struct.pack_into('>H', ip_header, 10, ip_checksum)
        
        # TCP header (20 bytes)
        src_port = self.source_port
        dst_port = self.target_port
        seq_num = random.randint(0, 0xFFFFFFFF)
        ack_num = random.randint(0, 0xFFFFFFFF)
        tcp_hdr_len = 5  # 5 * 4 = 20 bytes
        flags = 0x18  # ACK + PSH flags
        window_size = 8192
        checksum = 0  # Will calculate
        urgent_ptr = 0
        
        tcp_header = bytearray(20)
        struct.pack_into('>H', tcp_header, 0, src_port)
        struct.pack_into('>H', tcp_header, 2, dst_port)
        struct.pack_into('>I', tcp_header, 4, seq_num)
        struct.pack_into('>I', tcp_header, 8, ack_num)
        struct.pack_into('>H', tcp_header, 12, (tcp_hdr_len << 12) | flags)
        struct.pack_into('>H', tcp_header, 14, window_size)
        struct.pack_into('>H', tcp_header, 16, checksum)
        struct.pack_into('>H', tcp_header, 18, urgent_ptr)
        
        # Calculate TCP checksum (pseudo header + TCP header + data)
        pseudo_header = bytearray(12)
        pseudo_header[0:4] = src_ip
        pseudo_header[4:8] = dst_ip
        pseudo_header[8] = 0
        pseudo_header[9] = 6  # TCP protocol
        struct.pack_into('>H', pseudo_header, 10, 20 + len(http_content))
        
        tcp_checksum_data = pseudo_header + tcp_header + http_content
        tcp_checksum = self._calculate_checksum(tcp_checksum_data)
        struct.pack_into('>H', tcp_header, 16, tcp_checksum)
        
        # Combine all parts
        return bytes(eth_header + ip_header + tcp_header + http_content)
    
    def _calculate_checksum(self, data: bytearray) -> int:
        """Calculate IP/TCP checksum"""
        checksum = 0
        for i in range(0, len(data), 2):
            if i + 1 < len(data):
                checksum += (data[i] << 8) + data[i + 1]
            else:
                checksum += data[i] << 8
        
        while checksum >> 16:
            checksum = (checksum & 0xFFFF) + (checksum >> 16)
        
        return ~checksum & 0xFFFF
    
    def _ip_to_bytes(self, ip_str: str) -> bytes:
        """Convert IP string to bytes"""
        return bytes(map(int, ip_str.split('.')))
    
    def get_available_profiles(self) -> List[str]:
        """Get list of available profiles"""
        return list(self.PROFILES.keys())


def blast_onvif_packets(host: str, port: int, pps: int, seconds: int, 
                       profile: str = None, packet_type: str = None,
                       zoom_value: float = None, measurement_value: float = None,
                       source_ip: str = "192.168.1.102", source_port: int = 12346,
                       use_raw_socket: bool = True):
    """
    Sends ONVIF packets at ~pps using 10ms ticks (pps/100 per tick).
    Example: pps=100 -> 1 packet every 10ms.
    
    Args:
        use_raw_socket: If True, uses raw socket (requires root). If False, uses TCP socket.
    """
    builder = OnVIFPacketBuilder(host, port, source_ip, source_port)
    
    # Validate profile if provided
    if profile is not None and profile not in builder.get_available_profiles():
        available_profiles = builder.get_available_profiles()
        print(f"Warning: Profile '{profile}' not available")
        print(f"Available profiles: {available_profiles}")
        profile = random.choice(available_profiles)
        print(f"Using random profile: {profile}")
    
    # Validate packet type if provided
    if packet_type is not None and packet_type not in ["CMD", "RPT"]:
        print(f"Warning: Packet type '{packet_type}' not valid. Using random.")
        packet_type = random.choice(["CMD", "RPT"])
    
    # Choose socket type based on mode
    if use_raw_socket:
        try:
            # On macOS, use BPF (Berkeley Packet Filter) for raw socket access
            # This requires root privileges
            import platform
            if platform.system() == "Darwin":  # macOS
                # Use raw socket with IPPROTO_RAW on macOS
                sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
                print("Using raw socket mode on macOS (requires root privileges)")
            else:
                # Linux raw socket
                sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))  # ETH_P_ALL
                print("Using raw socket mode on Linux (requires root privileges)")
        except (PermissionError, OSError) as e:
            print(f"Raw socket failed: {e}. Falling back to TCP mode.")
            use_raw_socket = False
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((host, port))
            print("Using TCP socket mode")
        except ConnectionRefusedError:
            print(f"Connection refused to {host}:{port}. Make sure the target is listening.")
            return
    
    tick_hz = 100  # 100 ticks/sec -> 10ms per tick
    pkts_per_tick = max(1, pps // tick_hz)
    tick_interval = 1.0 / tick_hz
    
    end_time = time.perf_counter() + seconds
    next_tick = time.perf_counter()
    sent_total = 0
    
    print(f"Blasting ONVIF packets to {host}:{port}")
    print(f"Rate: ~{pps} pps, Duration: {seconds}s")
    if profile is not None:
        print(f"Profile: {profile}")
    else:
        print("Profile: Random")
    if packet_type is not None:
        print(f"Packet type: {packet_type}")
    else:
        print("Packet type: Random")
    if zoom_value is not None:
        print(f"Zoom value: {zoom_value}")
    if measurement_value is not None:
        print(f"Measurement value: {measurement_value}")
    print()
    
    while time.perf_counter() < end_time:
        # Send a burst for this tick
        for _ in range(pkts_per_tick):
            try:
                if use_raw_socket:
                    # Build complete Ethernet frame with current parameters
                    current_profile = profile or random.choice(builder.get_available_profiles())
                    current_type = packet_type or random.choice(["CMD", "RPT"])
                    packet_data = builder.build_packet(current_profile, current_type, zoom_value, measurement_value)
                    # Send raw Ethernet frame to destination
                    sock.sendto(packet_data, (host, 0))  # Port 0 for raw socket
                else:
                    # For TCP mode, send just the HTTP content
                    current_profile = profile or random.choice(builder.get_available_profiles())
                    current_type = packet_type or random.choice(["CMD", "RPT"])
                    
                    if current_type == "CMD":
                        xml_content = builder._build_cmd_xml(current_profile, str(uuid.uuid4()))
                        http_content = builder._build_http_request(xml_content)
                    else:
                        xml_content = builder._build_rpt_xml(current_profile, str(uuid.uuid4()), zoom_value, measurement_value)
                        http_content = builder._build_http_response(xml_content)
                    
                    sock.send(http_content)
                sent_total += 1
            except OSError as e:
                # Skip increment on failure; continue trying
                print(f"Send error: {e}")
                pass
        
        next_tick += tick_interval
        # Coarse sleep; then spin if needed
        now = time.perf_counter()
        sleep_s = next_tick - now
        if sleep_s > 0.002:  # Coarse sleep for >=2ms
            time.sleep(sleep_s - 0.001)
        while time.perf_counter() < next_tick:
            pass
    
    print(f"Done. Sent {sent_total} ONVIF packets.")
    sock.close()


def main():
    parser = argparse.ArgumentParser(
        description="ONVIF Packet Blaster - Fires TCP packets with proper ONVIF/SOAP XML format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage - random profile/type
  python onvif_blaster.py --host 192.168.1.100 --port 8080 --pps 100 --seconds 10
  
  # Specific profile and type
  python onvif_blaster.py --host 192.168.1.100 --port 8080 --pps 500 --seconds 30 --profile DAY --type CMD
  
  # LRF measurement response with specific value
  python onvif_blaster.py --host 192.168.1.100 --port 8080 --pps 200 --seconds 20 --profile LRF --type RPT --measurement 1234.5
  
  # DAY zoom response with specific zoom value
  python onvif_blaster.py --host 192.168.1.100 --port 8080 --pps 300 --seconds 15 --profile DAY --type RPT --zoom 0.75
  
  # Start mock server mode (for packet sniffing)
  python onvif_blaster.py --server --port 54321

Profiles:
  DAY: Day camera with zoom control
  IR:  Infrared camera with zoom control  
  LRF: Laser range finder with measurement
        """
    )
    
    parser.add_argument("--server", action="store_true", help="Start mock HTTP server mode instead of blasting packets")
    parser.add_argument("--host", help="Target IP address (required for blaster mode)")
    parser.add_argument("--port", type=int, default=8080, help="Target TCP port (default: 8080)")
    parser.add_argument("--pps", type=int, default=100, help="Packets per second (default: 100)")
    parser.add_argument("--seconds", type=int, default=10, help="Runtime in seconds (default: 10)")
    parser.add_argument("--profile", choices=["DAY", "IR", "LRF"], help="Profile type (DAY, IR, LRF). Random if not specified.")
    parser.add_argument("--type", choices=["CMD", "RPT"], help="Packet type (CMD, RPT). Random if not specified.")
    parser.add_argument("--zoom", type=float, help="Zoom value for DAY/IR responses (0.0-1.0). Random if not specified.")
    parser.add_argument("--measurement", type=float, help="Measurement value for LRF responses. Random if not specified.")
    parser.add_argument("--source-ip", default="192.168.1.102", help="Source IP address (default: 192.168.1.102)")
    parser.add_argument("--source-port", type=int, default=12346, help="Source TCP port (default: 12346)")
    parser.add_argument("--raw-socket", action="store_true", help="Use raw socket (requires root). If not specified, uses TCP socket.")
    
    args = parser.parse_args()
    
    # Handle server mode
    if args.server:
        print("Starting ONVIF Mock HTTP Server...")
        print(f"Server will listen on 0.0.0.0:{args.port}")
        print("This server will receive ONVIF requests and generate responses.")
        print("The PacketProcessing service can sniff these packets for testing.")
        print("Press Ctrl+C to stop the server.")
        print()
        
        try:
            start_mock_server("0.0.0.0", args.port)
            # Keep the main thread alive
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nServer stopped by user")
        return 0
    
    # Validate required arguments for blaster mode
    if not args.host:
        parser.error("--host is required for blaster mode (use --server for server mode)")
    
    try:
        blast_onvif_packets(
            host=args.host,
            port=args.port,
            pps=args.pps,
            seconds=args.seconds,
            profile=args.profile,
            packet_type=args.type,
            zoom_value=args.zoom,
            measurement_value=args.measurement,
            source_ip=args.source_ip,
            source_port=args.source_port,
            use_raw_socket=args.raw_socket
        )
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
