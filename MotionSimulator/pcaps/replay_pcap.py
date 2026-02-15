import sys
import time
import socket
import argparse
import os
from collections import defaultdict

try:
    from scapy.all import rdpcap, TCP, IP
except ImportError:
    print("Error: 'scapy' module not found.")
    print("Please install it using: pip install scapy")
    sys.exit(1)

def replay_pcap(pcap_path, target_ip, target_port, speed_multiplier=1.0):
    print(f"[PCAP Replay] Loading {pcap_path}...")
    try:
        packets = rdpcap(pcap_path)
    except Exception as e:
        print(f"[PCAP Replay] Failed to load pcap: {e}")
        return

    print(f"[PCAP Replay] Loaded {len(packets)} packets. Identifying client flows...")

    # Establish connection
    print(f"[PCAP Replay] Connecting to {target_ip}:{target_port}...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1) # Disable Nagle
        s.connect((target_ip, target_port))
        print(f"[PCAP Replay] Connected.")
    except Exception as e:
        print(f"[PCAP Replay] Connection failed: {e}")
        return

    start_time = None
    first_pkt_time = None
    start_time = None
    first_pkt_time = None
    packet_count = 0
    opcode_counts = defaultdict(int)
    
    try:
        for pkt in packets:
            if not pkt.haslayer(TCP):
                continue
                
            payload = bytes(pkt[TCP].payload)
            if not payload:
                continue

            # Timing synchronization
            pkt_time = float(pkt.time)
            if first_pkt_time is None:
                first_pkt_time = pkt_time
                start_time = time.time()
            
            # Calculate how much time has passed in the pcap vs real time
            pcap_delta = (pkt_time - first_pkt_time) / speed_multiplier
            real_delta = time.time() - start_time
            
            wait_time = pcap_delta - real_delta
            if wait_time > 0:
                time.sleep(wait_time)
            else:
                 # Force a tiny sleep to allow OS to flush buffer associated with previous packet
                 time.sleep(0.0005) 

            try:
                # Stats collection
                if len(payload) >= 7:
                    # Opcode is at index 5 and 6 (Big Endian)
                    opcode = (payload[5] << 8) | payload[6]
                    opcode_counts[opcode] += 1
                
                s.sendall(payload)
                packet_count += 1
                sys.stdout.write(f"\r[PCAP Replay] Sent packet {packet_count} (Size: {len(payload)})   ")
                sys.stdout.flush()
            except Exception as e:
                print(f"\n[PCAP Replay] Send failed: {e}")
                break
                
    except KeyboardInterrupt:
        print("\n[PCAP Replay] Interrupted by user.")
    finally:
        s.close()
        print(f"\n[PCAP Replay] Finished. Sent {packet_count} packets.")
        print("\n=== Opcode Statistics ===")
        print(f"{'Opcode':<10} {'Count':<10}")
        print("-" * 22)
        for op in sorted(opcode_counts.keys()):
            print(f"0x{op:04X}     {opcode_counts[op]:<10}")
        print("=========================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay TCP payload from pcap to a local port.")
    parser.add_argument("pcap_file", help="Path to pcap file")
    parser.add_argument("--host", default="127.0.0.1", help="Target host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=4949, help="Target port (default: 4949)")
    parser.add_argument("--speed", type=float, default=1.0, help="Speed multiplier (default: 1.0)")

    args = parser.parse_args()
    
    if not os.path.exists(args.pcap_file):
        print(f"Error: File {args.pcap_file} does not exist.")
        sys.exit(1)
        
    replay_pcap(args.pcap_file, args.host, args.port, args.speed)
