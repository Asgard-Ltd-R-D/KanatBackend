import sys
import time
import socket
import argparse
import os
from collections import defaultdict

try:
    from scapy.all import rdpcap, TCP, UDP, IP
except ImportError:
    print("Error: 'scapy' module not found.")
    print("Please install it using: pip install scapy")
    sys.exit(1)


def detect_protocol(packets):
    """Auto-detect TCP or UDP from first packet that has a payload."""
    for pkt in packets:
        if pkt.haslayer(TCP) and bytes(pkt[TCP].payload):
            return "tcp"
        if pkt.haslayer(UDP) and bytes(pkt[UDP].payload):
            return "udp"
    return None


def replay_pcap(pcap_path, target_ip, target_port, proto=None, speed_multiplier=1.0):
    print(f"[PCAP Replay] Loading {pcap_path}...")
    try:
        packets = rdpcap(pcap_path)
    except Exception as e:
        print(f"[PCAP Replay] Failed to load pcap: {e}")
        return

    print(f"[PCAP Replay] Loaded {len(packets)} packets.")

    if proto is None:
        proto = detect_protocol(packets)
        if proto is None:
            print("[PCAP Replay] Could not detect protocol. Use --proto tcp or --proto udp.")
            return
        print(f"[PCAP Replay] Auto-detected protocol: {proto.upper()}")
    else:
        print(f"[PCAP Replay] Protocol: {proto.upper()}")

    if proto == "tcp":
        _replay_tcp(packets, target_ip, target_port, speed_multiplier)
    else:
        _replay_udp(packets, target_port, speed_multiplier)


def _replay_tcp(packets, target_ip, target_port, speed_multiplier):
    print(f"[PCAP Replay] Connecting to {target_ip}:{target_port}...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.connect((target_ip, target_port))
        print("[PCAP Replay] Connected.")
    except Exception as e:
        print(f"[PCAP Replay] Connection failed: {e}")
        return

    _send_packets(packets, s, target_port, TCP, show_opcodes=True, speed_multiplier=speed_multiplier)


def _replay_udp(packets, target_port, speed_multiplier):
    print(f"[PCAP Replay] Sending UDP (destination from pcap, port filter: {target_port})...")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print("[PCAP Replay] Ready.")
    _send_udp_packets(packets, s, target_port, speed_multiplier)


def _iter_udp_payloads(packets, target_port):
    """Yield (pkt_time, payload, dst_ip, dst_port) for every matching UDP packet."""
    for pkt in packets:
        if not pkt.haslayer(UDP) or not pkt.haslayer(IP):
            continue
        layer = pkt[UDP]
        if layer.dport != target_port and layer.sport != target_port:
            continue
        payload = bytes(layer.payload)
        if payload:
            yield float(pkt.time), payload, pkt[IP].dst, layer.dport


def _print_dest_summary(dest_counts):
    if not dest_counts:
        return
    print("\n=== Destination Breakdown ===")
    for dst, count in sorted(dest_counts.items()):
        print(f"  {dst}: {count} packets")
    print("=============================")


def _send_udp_packets(packets, s, target_port, speed_multiplier):
    """Send UDP packets using destination IP/port from the pcap (supports multiple destinations)."""
    start_time = None
    first_pkt_time = None
    packet_count = 0
    dest_counts = defaultdict(int)

    try:
        for pkt_time, payload, dst_ip, dst_port in _iter_udp_payloads(packets, target_port):
            if first_pkt_time is None:
                first_pkt_time = pkt_time
                start_time = time.time()

            wait = (pkt_time - first_pkt_time) / speed_multiplier - (time.time() - start_time)
            time.sleep(max(wait, 0.0005))

            try:
                s.sendto(payload, (dst_ip, dst_port))
                packet_count += 1
                dest_counts[dst_ip] += 1
                sys.stdout.write(f"\r[PCAP Replay] Sent packet {packet_count} → {dst_ip}:{dst_port} (Size: {len(payload)})   ")
                sys.stdout.flush()
            except Exception as e:
                print(f"\n[PCAP Replay] Send failed: {e}")
                break

    except KeyboardInterrupt:
        print("\n[PCAP Replay] Interrupted by user.")
    finally:
        s.close()
        print(f"\n[PCAP Replay] Finished. Sent {packet_count} packets.")
        _print_dest_summary(dest_counts)


def _send_packets(packets, s, target_port, layer_class, show_opcodes, speed_multiplier):
    start_time = None
    first_pkt_time = None
    packet_count = 0
    opcode_counts = defaultdict(int)

    try:
        for pkt in packets:
            if not pkt.haslayer(layer_class):
                continue

            layer = pkt[layer_class]
            if layer.dport != target_port and layer.sport != target_port:
                continue

            payload = bytes(layer.payload)
            if not payload:
                continue

            pkt_time = float(pkt.time)
            if first_pkt_time is None:
                first_pkt_time = pkt_time
                start_time = time.time()

            pcap_delta = (pkt_time - first_pkt_time) / speed_multiplier
            real_delta = time.time() - start_time
            wait_time = pcap_delta - real_delta
            if wait_time > 0:
                time.sleep(wait_time)
            else:
                time.sleep(0.0005)

            try:
                if show_opcodes and len(payload) >= 7:
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
        if show_opcodes and opcode_counts:
            print("\n=== Opcode Statistics ===")
            print(f"{'Opcode':<10} {'Count':<10}")
            print("-" * 22)
            for op in sorted(opcode_counts.keys()):
                print(f"0x{op:04X}     {opcode_counts[op]:<10}")
            print("=========================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay TCP or UDP payload from pcap to a local port.")
    parser.add_argument("pcap_file", help="Path to pcap file")
    parser.add_argument("--host", default="127.0.0.1", help="Target host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=4949, help="Target port (default: 4949)")
    parser.add_argument("--proto", choices=["tcp", "udp"], default=None, help="Protocol override (default: auto-detect)")
    parser.add_argument("--speed", type=float, default=1.0, help="Speed multiplier (default: 1.0)")

    args = parser.parse_args()

    if not os.path.exists(args.pcap_file):
        print(f"Error: File {args.pcap_file} does not exist.")
        sys.exit(1)

    replay_pcap(args.pcap_file, args.host, args.port, args.proto, args.speed)
