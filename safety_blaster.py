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
        Builds a Safety PDU payload for UDP transmission.
        The OS will add IP and UDP headers automatically.
        
        Returns only the Safety/Modbus-like PDU (20 bytes)
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
    
    def _ip_to_bytes(self, ip_str: str) -> bytes:
        """Convert IP string to bytes"""
        return bytes(map(int, ip_str.split('.')))
    
    def get_available_do_codes(self) -> List[int]:
        """Get list of available DO codes for current target"""
        return self.available_do_codes.copy()
    
    def get_available_state_codes(self) -> List[int]:
        """Get list of available state codes"""
        return list(self.STATE_CODES.keys())


def blast_safety_packets(host: str, port: int, pps: int, seconds: int, 
                        do_code: int = None, state_code: int = None,
                        source_ip: str = "192.168.1.100", source_port: int = 12345):
    """
    Sends safety packets at ~pps using 10ms ticks (pps/100 per tick).
    Example: pps=10_000 -> 100 packets every 10ms.
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
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
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
                # Build packet with current parameters
                packet_data = builder.build_packet(do_code, state_code, sent_total + 1)
                sock.sendto(packet_data, (host, port))
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
            source_port=args.source_port
        )
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
