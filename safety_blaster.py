#!/usr/bin/env python3
"""
Safety Packet Blaster

Fires UDP packets with proper safety entity binary format at specified rate.
The packets match the expected parser format for SafetyPacketEntity.

Usage:
    python safety_blaster.py --host 132.8.7.101 --port 54321 --pps 1000 --seconds 10
    python safety_blaster.py --host 132.8.7.102 --port 54321 --pps 5000 --seconds 30 --do-code 0x0010 --state 0xFF00
"""

import argparse
import socket
import time
import struct
import random
from typing import List, Tuple


class SafetyPacketBuilder:
    """Builds safety packets with proper binary format for the parser"""
    
    # DO codes for PBE (132.8.7.101)
    DO_PBE = {
        0x0010: "1",
        0x0027: "DO3_FIRE1", 
        0x0012: "DO2_MOTION",
        0x0014: "DO4_LED_FIRE_EN"
    }
    
    # DO codes for SBE (132.8.7.102)
    DO_SBE = {
        0x0010: "DO0_RLD",
        0x0011: "DO1_RLD_SFTY",
        0x0012: "DO2_PWR",
        0x0028: "DO4_FIRE2",
        0x0015: "X5"
    }
    
    # State codes
    STATE_CODES = {
        0x0000: "OFF",
        0xFF00: "ON", 
        0x0001: "PULSE",
        0x0003: "BURST"
    }
    
    def __init__(self, target_ip: str, target_port: int, source_ip: str = "192.168.1.100", source_port: int = 12345):
        self.target_ip = target_ip
        self.target_port = target_port
        self.source_ip = source_ip
        self.source_port = source_port
        
        # Parse target IP to determine if PBE or SBE
        self.is_pbe = target_ip == "132.8.7.101"
        self.is_sbe = target_ip == "132.8.7.102"
        
        # Get available DO codes for this target
        self.available_do_codes = list(self.DO_PBE.keys()) if self.is_pbe else list(self.DO_SBE.keys())
    
    def build_packet(self, do_code: int = None, state_code: int = None, tid: int = None) -> bytes:
        """
        Builds a complete Ethernet frame with Safety PDU for raw socket transmission.
        This matches what the SafetyPacketParser expects.
        
        Returns complete Ethernet frame (14 + 20 + 8 + 20 = 62 bytes minimum)
        """
        if do_code is None:
            do_code = random.choice(self.available_do_codes)
        if state_code is None:
            state_code = random.choice(list(self.STATE_CODES.keys()))
        if tid is None:
            tid = random.randint(1, 65535)
        
        # Safety/Modbus-like PDU (20 bytes)
        pdu = bytearray(20)
        struct.pack_into('>H', pdu, 0, tid)  # TID
        struct.pack_into('>H', pdu, 2, 0x0000)  # PID
        struct.pack_into('>H', pdu, 4, 0x000E)  # Length
        struct.pack_into('>B', pdu, 6, 0x01)  # UnitID
        struct.pack_into('>B', pdu, 7, 0x06)  # FunctionCode
        # params 1-4 (8 bytes) - all zeros
        struct.pack_into('>H', pdu, 16, do_code)  # DO
        struct.pack_into('>H', pdu, 18, state_code)  # STATE
        
        # Build complete Ethernet frame
        return self._build_ethernet_frame(bytes(pdu))
    
    def _build_ethernet_frame(self, pdu: bytes) -> bytes:
        """Builds complete Ethernet frame with IP and UDP headers"""
        # Ethernet header (14 bytes)
        dst_mac = b'\xff\xff\xff\xff\xff\xff'  # Broadcast MAC
        src_mac = b'\x00\x11\x22\x33\x44\x55'  # Fake source MAC
        eth_type = b'\x08\x00'  # IPv4 (0x0800)
        eth_header = dst_mac + src_mac + eth_type
        
        # IPv4 header (20 bytes)
        version_ihl = 0x45  # Version 4, IHL 5 (20 bytes)
        tos = 0x00  # Type of Service
        total_length = 20 + 8 + len(pdu)  # IP header + UDP header + PDU
        identification = random.randint(0, 65535)
        flags_fragment = 0x4000  # Don't fragment
        ttl = 64
        protocol = 17  # UDP
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
        
        # UDP header (8 bytes)
        src_port = self.source_port
        dst_port = self.target_port
        udp_length = 8 + len(pdu)
        udp_checksum = 0  # Optional for UDP
        
        udp_header = bytearray(8)
        struct.pack_into('>H', udp_header, 0, src_port)
        struct.pack_into('>H', udp_header, 2, dst_port)
        struct.pack_into('>H', udp_header, 4, udp_length)
        struct.pack_into('>H', udp_header, 6, udp_checksum)
        
        # Combine all parts
        return bytes(eth_header + ip_header + udp_header + pdu)
    
    def _calculate_checksum(self, data: bytearray) -> int:
        """Calculate IP checksum"""
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
    
    def get_available_do_codes(self) -> List[int]:
        """Get list of available DO codes for current target"""
        return self.available_do_codes.copy()
    
    def get_available_state_codes(self) -> List[int]:
        """Get list of available state codes"""
        return list(self.STATE_CODES.keys())
    
    def _build_pdu_only(self, do_code: int = None, state_code: int = None, tid: int = None) -> bytes:
        """
        Builds only the Safety PDU payload for UDP transmission (legacy mode).
        This is used when not using raw sockets.
        """
        if do_code is None:
            do_code = random.choice(self.available_do_codes)
        if state_code is None:
            state_code = random.choice(list(self.STATE_CODES.keys()))
        if tid is None:
            tid = random.randint(1, 65535)
        
        # Safety/Modbus-like PDU (20 bytes)
        pdu = bytearray(20)
        struct.pack_into('>H', pdu, 0, tid)  # TID
        struct.pack_into('>H', pdu, 2, 0x0000)  # PID
        struct.pack_into('>H', pdu, 4, 0x000E)  # Length
        struct.pack_into('>B', pdu, 6, 0x01)  # UnitID
        struct.pack_into('>B', pdu, 7, 0x06)  # FunctionCode
        # params 1-4 (8 bytes) - all zeros
        struct.pack_into('>H', pdu, 16, do_code)  # DO
        struct.pack_into('>H', pdu, 18, state_code)  # STATE
        
        return bytes(pdu)
    
    def _build_ip_packet(self, do_code: int = None, state_code: int = None, tid: int = None) -> bytes:
        """
        Builds IP packet with UDP header and Safety PDU for macOS raw socket.
        This creates IP + UDP + PDU (no Ethernet header for macOS raw sockets).
        """
        if do_code is None:
            do_code = random.choice(self.available_do_codes)
        if state_code is None:
            state_code = random.choice(list(self.STATE_CODES.keys()))
        if tid is None:
            tid = random.randint(1, 65535)
        
        # Safety/Modbus-like PDU (20 bytes)
        pdu = bytearray(20)
        struct.pack_into('>H', pdu, 0, tid)  # TID
        struct.pack_into('>H', pdu, 2, 0x0000)  # PID
        struct.pack_into('>H', pdu, 4, 0x000E)  # Length
        struct.pack_into('>B', pdu, 6, 0x01)  # UnitID
        struct.pack_into('>B', pdu, 7, 0x06)  # FunctionCode
        # params 1-4 (8 bytes) - all zeros
        struct.pack_into('>H', pdu, 16, do_code)  # DO
        struct.pack_into('>H', pdu, 18, state_code)  # STATE
        
        # IPv4 header (20 bytes)
        version_ihl = 0x45  # Version 4, IHL 5 (20 bytes)
        tos = 0x00  # Type of Service
        total_length = 20 + 8 + len(pdu)  # IP header + UDP header + PDU
        identification = random.randint(0, 65535)
        flags_fragment = 0x4000  # Don't fragment
        ttl = 64
        protocol = 17  # UDP
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
        
        # UDP header (8 bytes)
        src_port = self.source_port
        dst_port = self.target_port
        udp_length = 8 + len(pdu)
        udp_checksum = 0  # Optional for UDP
        
        udp_header = bytearray(8)
        struct.pack_into('>H', udp_header, 0, src_port)
        struct.pack_into('>H', udp_header, 2, dst_port)
        struct.pack_into('>H', udp_header, 4, udp_length)
        struct.pack_into('>H', udp_header, 6, udp_checksum)
        
        # Combine IP + UDP + PDU
        return bytes(ip_header + udp_header + pdu)


def blast_safety_packets(host: str, port: int, pps: int, seconds: int, 
                        do_code: int = None, state_code: int = None,
                        source_ip: str = "192.168.1.100", source_port: int = 12345,
                        use_raw_socket: bool = True):
    """
    Sends safety packets at ~pps using 10ms ticks (pps/100 per tick).
    Example: pps=10_000 -> 100 packets every 10ms.
    
    Args:
        use_raw_socket: If True, uses raw socket (requires root). If False, uses UDP socket.
    """
    builder = SafetyPacketBuilder(host, port, source_ip, source_port)
    
    # Validate DO code if provided
    if do_code is not None and do_code not in builder.get_available_do_codes():
        available_codes = builder.get_available_do_codes()
        print(f"Warning: DO code 0x{do_code:04X} not available for target {host}")
        print(f"Available DO codes: {[f'0x{code:04X}' for code in available_codes]}")
        do_code = random.choice(available_codes)
        print(f"Using random DO code: 0x{do_code:04X}")
    
    # Validate state code if provided
    if state_code is not None and state_code not in builder.get_available_state_codes():
        available_states = builder.get_available_state_codes()
        print(f"Warning: State code 0x{state_code:04X} not available")
        print(f"Available state codes: {[f'0x{code:04X}' for code in available_states]}")
        state_code = random.choice(available_states)
        print(f"Using random state code: 0x{state_code:04X}")
    
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
            print(f"Raw socket failed: {e}. Falling back to UDP mode.")
            use_raw_socket = False
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print("Using UDP socket mode")
    
    tick_hz = 100  # 100 ticks/sec -> 10ms per tick
    pkts_per_tick = max(1, pps // tick_hz)
    tick_interval = 1.0 / tick_hz
    
    end_time = time.perf_counter() + seconds
    next_tick = time.perf_counter()
    sent_total = 0
    
    # Determine target type
    target_type = "PBE" if builder.is_pbe else "SBE" if builder.is_sbe else "Unknown"
    
    print(f"Blasting safety packets to {host}:{port} ({target_type})")
    print(f"Rate: ~{pps} pps, Duration: {seconds}s")
    if do_code is not None:
        print(f"DO code: 0x{do_code:04X}")
    else:
        print("DO code: Random")
    if state_code is not None:
        print(f"State: 0x{state_code:04X}")
    else:
        print("State: Random")
    print(f"Available DO codes: {[f'0x{code:04X}' for code in builder.get_available_do_codes()]}")
    print(f"Available states: {[f'0x{code:04X}' for code in builder.get_available_state_codes()]}")
    print()
    
    while time.perf_counter() < end_time:
        # Send a burst for this tick
        for _ in range(pkts_per_tick):
            try:
                if use_raw_socket:
                    # Build complete IP packet with current parameters (no Ethernet header for macOS)
                    packet_data = builder._build_ip_packet(do_code, state_code, sent_total + 1)
                    # Send raw IP packet to destination
                    sock.sendto(packet_data, (host, 0))  # Port 0 for raw socket
                else:
                    # For UDP mode, we need to modify the builder to return just the PDU
                    # and let the OS handle IP/UDP headers
                    pdu_data = builder._build_pdu_only(do_code, state_code, sent_total + 1)
                    sock.sendto(pdu_data, (host, port))
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
    
    print(f"Done. Sent {sent_total} safety packets.")
    sock.close()


def main():
    parser = argparse.ArgumentParser(
        description="Safety Packet Blaster - Fires UDP packets with proper safety entity binary format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage - random DO/state codes
  python safety_blaster.py --host 132.8.7.101 --port 54321 --pps 1000 --seconds 10
  
  # Specific DO and state codes
  python safety_blaster.py --host 132.8.7.102 --port 54321 --pps 5000 --seconds 30 --do-code 0x0010 --state 0xFF00
  
  # High rate test
  python safety_blaster.py --host 132.8.7.101 --port 54321 --pps 10000 --seconds 60

Available DO codes:
  PBE (132.8.7.101): 0x0010, 0x0027, 0x0012, 0x0014
  SBE (132.8.7.102): 0x0010, 0x0011, 0x0012, 0x0028, 0x0015

Available states: 0x0000 (OFF), 0xFF00 (ON), 0x0001 (PULSE), 0x0003 (BURST)
        """
    )
    
    parser.add_argument("--host", required=True, help="Target IP address (e.g., 132.8.7.101 for PBE, 132.8.7.102 for SBE)")
    parser.add_argument("--port", type=int, default=54321, help="Target UDP port (default: 54321)")
    parser.add_argument("--pps", type=int, default=1000, help="Packets per second (default: 1000)")
    parser.add_argument("--seconds", type=int, default=10, help="Runtime in seconds (default: 10)")
    parser.add_argument("--do-code", type=lambda x: int(x, 0), help="DO code in hex (e.g., 0x0010). Random if not specified.")
    parser.add_argument("--state", type=lambda x: int(x, 0), help="State code in hex (e.g., 0xFF00). Random if not specified.")
    parser.add_argument("--source-ip", default="192.168.1.100", help="Source IP address (default: 192.168.1.100)")
    parser.add_argument("--source-port", type=int, default=12345, help="Source UDP port (default: 12345)")
    parser.add_argument("--raw-socket", action="store_true", help="Use raw socket (requires root). If not specified, uses UDP socket.")
    
    args = parser.parse_args()
    
    try:
        blast_safety_packets(
            host=args.host,
            port=args.port,
            pps=args.pps,
            seconds=args.seconds,
            do_code=args.do_code,
            state_code=args.state,
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
