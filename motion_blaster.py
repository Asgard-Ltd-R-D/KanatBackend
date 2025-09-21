#!/usr/bin/env python3
"""
Motion Packet Blaster

Fires TCP packets with proper motion entity binary format at specified rate.
The packets match the expected parser format for MotionPacketEntity using CapTrack protocol.

Usage:
    python motion_blaster.py --host 192.168.1.100 --port 8080 --pps 1000 --seconds 10
    python motion_blaster.py --host 192.168.1.100 --port 8080 --pps 5000 --seconds 30 --opcode 0x0108 --axis 1
"""

import argparse
import socket
import time
import struct
import random
import threading
from typing import List, Tuple


class MotionPacketBuilder:
    """Builds motion packets with proper binary format for the parser"""
    
    # Opcode descriptions (subset of the full list)
    OPCODES = {
        0x0101: "MOT_MerRegister",
        0x0102: "MOT_DerRegister", 
        0x0103: "MOT_SrhRegister",
        0x0104: "MOT_SrlRegister",
        0x0105: "MOT_MsrRegister",
        0x0106: "MOT_GetMotorCurrent",
        0x0107: "MOT_GetMotorVoltage",
        0x0108: "MOT_GetMotorPosition",
        0x0109: "MOT_GetLoadPosition",
        0x010A: "MOT_GetMotorSpeed",
        0x010C: "MOT_GetNegSWLS",
        0x010D: "MOT_GetPosSWLS",
        0x0110: "MOT_IsActiveSWLS",
        0x012E: "MOT_GetMaxCurrent",
        0x0130: "MOT_SetAcceleration",
        0x0131: "MOT_SetSpeed",
        0x0132: "MOT_SendPosition",
        0x0133: "MOT_SetActualPosition",
        0x0134: "MOT_Update",
        0x0135: "MOT_Homing",
        0x0136: "MOT_SetNegSWLS",
        0x0137: "MOT_SetPosSWLS",
        0x0138: "MOT_SetPositionRelative",
        0x0139: "MOT_SetPositionAbsolute",
        0x013A: "MOT_SetSpeedMode",
        0x013B: "MOT_SetPositionMode",
        0x013C: "MOT_AxisOn",
        0x013D: "MOT_AxisOff",
        0x013E: "MOT_AxisReset",
        0x013F: "MOT_SetTum",
        0x0143: "MOT_ResetFaults",
        0x0144: "MOT_SetMotionComplete",
        0x0146: "MOT_ActivateSWLS",
        0x014E: "MOT_SetShortPath",
        0x014F: "MOT_GetShortPath",
        0x0165: "MOT_SaveMotorSetting",
        0x0166: "MOT_SetMaxCurrent",
        
        # SCN (scan) opcodes
        0x0400: "SCN_SetYawMin",
        0x0401: "SCN_SetYawMax",
        0x0402: "SCN_SetPitchMin",
        0x0403: "SCN_SetNumSteps",
        0x0404: "SCN_SetStepHeight",
        0x0405: "SCN_SetScanSpeed",
        0x0406: "SCN_SetShortPath",
        0x0407: "SCN_IsScanOn",
        0x0408: "SCN_StopScan",
        0x040C: "SCN_StartScanZigZag",
        0x040D: "SCN_StartScanSnake",
        0x040E: "SCN_StartScanSquare",
        
        # COM opcodes
        0x0700: "COM_Reboot",
        0x0702: "COM_Connect",
        0x0703: "COM_Disconnect",
        0x0704: "COM_IsConnected",
        0x0705: "COM_StartKeepAlive",
        0x0706: "COM_IsKeepAliveOn",
        0x0708: "COM_setKeepAliveTimeout",
        0x0709: "COM_getKeepAliveTimeout",
        0x0713: "COM_SysState",
        0x0719: "COM_SetComType",
        0x071C: "COM_setKeepAliveCount",
        0x071D: "COM_getKeepAliveCount"
    }
    
    def __init__(self, target_ip: str, target_port: int, source_ip: str = "192.168.1.101", source_port: int = 12345):
        self.target_ip = target_ip
        self.target_port = target_port
        self.source_ip = source_ip
        self.source_port = source_port
        self.available_opcodes = list(self.OPCODES.keys())
    
    def build_packet(self, opcode: int = None, axis_id: int = None, float_value: float = None, use_captrack: bool = True) -> bytes:
        """
        Builds a complete Ethernet frame with Motion PDU for raw socket transmission.
        This matches what the MotionPacketParser expects.
        
        Args:
            opcode: Motion opcode (default: random)
            axis_id: Axis ID (default: random 1-8)
            float_value: Float value to include (default: random)
            use_captrack: Whether to use CapTrack protocol header (0xCAFE)
        
        Returns complete Ethernet frame
        """
        if opcode is None:
            opcode = random.choice(self.available_opcodes)
        if axis_id is None:
            axis_id = random.randint(1, 8)
        if float_value is None:
            float_value = random.uniform(-1000.0, 1000.0)
        
        # Build CapTrack PDU
        if use_captrack:
            # CapTrack protocol with header (0xCAFE)
            pdu = bytearray(12)  # CapTrack header + opcode + float
            pdu[0] = 0xCA  # CapTrack magic byte 1
            pdu[1] = 0xFE  # CapTrack magic byte 2
            pdu[2] = 8     # Length
            pdu[3] = 0x01  # Group ID
            pdu[4] = axis_id  # Axis ID
            struct.pack_into('>H', pdu, 5, opcode)  # Opcode (big-endian)
            struct.pack_into('>f', pdu, 7, float_value)  # Float value (big-endian)
        else:
            # Direct PDU format (no CapTrack header)
            pdu = bytearray(8)
            struct.pack_into('>H', pdu, 0, opcode)  # Opcode (big-endian)
            pdu[2] = axis_id  # Axis ID
            # Note: Direct PDU format doesn't include float value in this implementation
        
        # Build complete Ethernet frame
        return self._build_ethernet_frame(bytes(pdu))
    
    def _build_ethernet_frame(self, pdu: bytes) -> bytes:
        """Builds complete Ethernet frame with IP and TCP headers"""
        # Ethernet header (14 bytes)
        dst_mac = b'\xff\xff\xff\xff\xff\xff'  # Broadcast MAC
        src_mac = b'\x00\x11\x22\x33\x44\x55'  # Fake source MAC
        eth_type = b'\x08\x00'  # IPv4 (0x0800)
        eth_header = dst_mac + src_mac + eth_type
        
        # IPv4 header (20 bytes)
        version_ihl = 0x45  # Version 4, IHL 5 (20 bytes)
        tos = 0x00  # Type of Service
        total_length = 20 + 20 + len(pdu)  # IP header + TCP header + PDU
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
        ack_num = 0
        tcp_hdr_len = 5  # 5 * 4 = 20 bytes
        flags = 0x02  # SYN flag
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
        struct.pack_into('>H', pseudo_header, 10, 20 + len(pdu))
        
        tcp_checksum_data = pseudo_header + tcp_header + pdu
        tcp_checksum = self._calculate_checksum(tcp_checksum_data)
        struct.pack_into('>H', tcp_header, 16, tcp_checksum)
        
        # Combine all parts
        return bytes(eth_header + ip_header + tcp_header + pdu)
    
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
    
    def get_available_opcodes(self) -> List[int]:
        """Get list of available opcodes"""
        return self.available_opcodes.copy()


def blast_motion_packets(host: str, port: int, pps: int, seconds: int, 
                        opcode: int = None, axis_id: int = None, float_value: float = None,
                        source_ip: str = "192.168.1.101", source_port: int = 12345,
                        use_raw_socket: bool = True, use_captrack: bool = True):
    """
    Sends motion packets at ~pps using 10ms ticks (pps/100 per tick).
    Example: pps=10_000 -> 100 packets every 10ms.
    
    Args:
        use_raw_socket: If True, uses raw socket (requires root). If False, uses TCP socket.
        use_captrack: If True, uses CapTrack protocol header (0xCAFE). If False, uses direct PDU.
    """
    builder = MotionPacketBuilder(host, port, source_ip, source_port)
    
    # Validate opcode if provided
    if opcode is not None and opcode not in builder.get_available_opcodes():
        available_opcodes = builder.get_available_opcodes()
        print(f"Warning: Opcode 0x{opcode:04X} not available")
        print(f"Available opcodes: {[f'0x{code:04X}' for code in available_opcodes[:10]]}...")
        opcode = random.choice(available_opcodes)
        print(f"Using random opcode: 0x{opcode:04X}")
    
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
    
    print(f"Blasting motion packets to {host}:{port}")
    print(f"Rate: ~{pps} pps, Duration: {seconds}s")
    print(f"Protocol: {'CapTrack' if use_captrack else 'Direct PDU'}")
    if opcode is not None:
        print(f"Opcode: 0x{opcode:04X} ({builder.OPCODES.get(opcode, 'Unknown')})")
    else:
        print("Opcode: Random")
    if axis_id is not None:
        print(f"Axis ID: {axis_id}")
    else:
        print("Axis ID: Random (1-8)")
    if float_value is not None:
        print(f"Float value: {float_value}")
    else:
        print("Float value: Random")
    print()
    
    while time.perf_counter() < end_time:
        # Send a burst for this tick
        for _ in range(pkts_per_tick):
            try:
                if use_raw_socket:
                    # Build complete Ethernet frame with current parameters
                    packet_data = builder.build_packet(opcode, axis_id, float_value, use_captrack)
                    # Send raw Ethernet frame to destination
                    sock.sendto(packet_data, (host, 0))  # Port 0 for raw socket
                else:
                    # For TCP mode, send just the PDU
                    if use_captrack:
                        pdu = bytearray(12)
                        pdu[0] = 0xCA
                        pdu[1] = 0xFE
                        pdu[2] = 8
                        pdu[3] = 0x01
                        pdu[4] = axis_id or random.randint(1, 8)
                        struct.pack_into('>H', pdu, 5, opcode or random.choice(builder.get_available_opcodes()))
                        struct.pack_into('>f', pdu, 7, float_value or random.uniform(-1000.0, 1000.0))
                    else:
                        pdu = bytearray(8)
                        struct.pack_into('>H', pdu, 0, opcode or random.choice(builder.get_available_opcodes()))
                        pdu[2] = axis_id or random.randint(1, 8)
                        # Direct PDU format doesn't include float value
                    
                    sock.send(bytes(pdu))
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
    
    print(f"Done. Sent {sent_total} motion packets.")
    sock.close()


def main():
    parser = argparse.ArgumentParser(
        description="Motion Packet Blaster - Fires TCP packets with proper motion entity binary format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage - random opcode/axis/float values
  python motion_blaster.py --host 192.168.1.100 --port 8080 --pps 1000 --seconds 10
  
  # Specific opcode and axis
  python motion_blaster.py --host 192.168.1.100 --port 8080 --pps 5000 --seconds 30 --opcode 0x0108 --axis 1
  
  # High rate test with CapTrack protocol
  python motion_blaster.py --host 192.168.1.100 --port 8080 --pps 10000 --seconds 60 --captrack
  
  # Direct PDU format (no CapTrack header)
  python motion_blaster.py --host 192.168.1.100 --port 8080 --pps 1000 --seconds 10 --no-captrack

Common opcodes:
  0x0108: MOT_GetMotorPosition
  0x0109: MOT_GetLoadPosition  
  0x010A: MOT_GetMotorSpeed
  0x0131: MOT_SetSpeed
  0x0132: MOT_SendPosition
  0x0135: MOT_Homing
        """
    )
    
    parser.add_argument("--host", required=True, help="Target IP address")
    parser.add_argument("--port", type=int, default=8080, help="Target TCP port (default: 8080)")
    parser.add_argument("--pps", type=int, default=1000, help="Packets per second (default: 1000)")
    parser.add_argument("--seconds", type=int, default=10, help="Runtime in seconds (default: 10)")
    parser.add_argument("--opcode", type=lambda x: int(x, 0), help="Opcode in hex (e.g., 0x0108). Random if not specified.")
    parser.add_argument("--axis", type=int, help="Axis ID (1-8). Random if not specified.")
    parser.add_argument("--float-value", type=float, help="Float value to include. Random if not specified.")
    parser.add_argument("--source-ip", default="192.168.1.101", help="Source IP address (default: 192.168.1.101)")
    parser.add_argument("--source-port", type=int, default=12345, help="Source TCP port (default: 12345)")
    parser.add_argument("--raw-socket", action="store_true", help="Use raw socket (requires root). If not specified, uses TCP socket.")
    parser.add_argument("--captrack", action="store_true", help="Use CapTrack protocol header (0xCAFE). Default: True")
    parser.add_argument("--no-captrack", action="store_true", help="Use direct PDU format (no CapTrack header)")
    
    args = parser.parse_args()
    
    # Determine CapTrack usage
    use_captrack = not args.no_captrack  # Default to True unless --no-captrack is specified
    
    try:
        blast_motion_packets(
            host=args.host,
            port=args.port,
            pps=args.pps,
            seconds=args.seconds,
            opcode=args.opcode,
            axis_id=args.axis,
            float_value=args.float_value,
            source_ip=args.source_ip,
            source_port=args.source_port,
            use_raw_socket=args.raw_socket,
            use_captrack=use_captrack
        )
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
