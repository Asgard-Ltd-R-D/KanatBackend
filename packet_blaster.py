#!/usr/bin/env python3
"""
packet_blaster.py

Features:
- Live UDP/TCP blast.
- Write PCAP files.
- Replay PCAP files over a given network interface (link-layer).
  * Preserves original addresses and timestamps automatically.
  * Optional payload/size randomization, shuffle, and loop.
"""

import argparse, os, socket, struct, time, random, sys
from typing import Optional, Tuple

try:
    from scapy.all import rdpcap, wrpcap, Ether, Raw, sendp
    SCAPY_AVAILABLE = True
except Exception:
    SCAPY_AVAILABLE = False

# -------------------------
# Utilities
# -------------------------
def now() -> float: return time.perf_counter()
def utc_time() -> float: return time.time()

# -------------------------
# Live blasters
# -------------------------
def blast_udp(host: str, port: int, pps: int, payload_size: int, seconds: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = os.urandom(payload_size)

    tick_hz = 100
    pkts_per_tick = max(1, pps // tick_hz)
    tick_interval = 1.0 / tick_hz

    end_time = now() + seconds
    next_tick = now()
    sent_total = 0
    print(f"UDP blasting {host}:{port} ~{pps}pps {payload_size}B for {seconds}s")

    while now() < end_time:
        for _ in range(pkts_per_tick):
            counter = sent_total & 0xFFFFFFFFFFFFFFFF
            buf = struct.pack(">Q", counter) + payload[8:] if payload_size >= 8 else payload
            try:
                sock.sendto(buf, (host, port))
                sent_total += 1
            except OSError:
                pass
        next_tick += tick_interval
        sleep_s = next_tick - now()
        if sleep_s > 0.002:
            time.sleep(sleep_s - 0.001)
        while now() < next_tick: pass

    print(f"Done. Sent {sent_total} packets.")
    sock.close()

def blast_tcp(host: str, port: int, pps: int, payload_size: int, seconds: int):
    payload = os.urandom(payload_size)
    tick_hz = 100
    pkts_per_tick = max(1, pps // tick_hz)
    tick_interval = 1.0 / tick_hz

    end_time = now() + seconds
    next_tick = now()
    sent_total = 0
    print(f"TCP blasting {host}:{port} ~{pps}pps {payload_size}B for {seconds}s")

    while now() < end_time:
        for _ in range(pkts_per_tick):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.0)
                s.connect((host, port))
                s.sendall(payload)
                s.close()
                sent_total += 1
            except OSError:
                pass
        next_tick += tick_interval
        sleep_s = next_tick - now()
        if sleep_s > 0.002:
            time.sleep(sleep_s - 0.001)
        while now() < next_tick: pass

    print(f"Done. Sent {sent_total} TCP sends.")

# -------------------------
# PCAP write & replay
# -------------------------
def write_pcap(path: str, packets: int, payload_size: int, pps: int):
    if not SCAPY_AVAILABLE:
        print("Install scapy: pip install scapy")
        return
    print(f"Writing PCAP: {path}, {packets} packets, {payload_size}B")
    pkt = Ether()/Raw(os.urandom(payload_size))
    t0 = utc_time()
    dt = 1.0 / pps
    frames = [(pkt, t0 + i*dt) for i in range(packets)]
    wrpcap(path, frames)
    print("PCAP written:", path)

def replay_pcap(path: str, iface: str, randomize_payload=False,
                randomize_size: Optional[Tuple[int,int]]=None,
                shuffle=False, loop=1):
    if not SCAPY_AVAILABLE:
        print("Install scapy: pip install scapy")
        return
    packets = rdpcap(path)
    frames = list(packets) * loop
    if shuffle: random.shuffle(frames)

    print(f"Replaying {len(frames)} frames from {path} on {iface}")
    for pkt in frames:
        if randomize_payload or randomize_size:
            if pkt.haslayer(Raw):
                size = len(pkt[Raw].load)
                if randomize_size: size = random.randint(*randomize_size)
                pkt[Raw].load = os.urandom(size) if randomize_payload else pkt[Raw].load
            else:
                size = random.randint(*randomize_size) if randomize_size else 64
                pkt = pkt/Raw(os.urandom(size))
        sendp(pkt, iface=iface, verbose=False)
    print("Replay complete.")

# -------------------------
# CLI
# -------------------------
def main():
    ap = argparse.ArgumentParser(description="Packet blaster / PCAP replayer")
    ap.add_argument("--mode", choices=["blast","pcap-out","replay"], required=True)

    # live blast
    ap.add_argument("--protocol", choices=["udp","tcp"], default="udp")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--pps", type=int, default=10000)
    ap.add_argument("--payload", type=int, default=256)
    ap.add_argument("--seconds", type=int, default=10)

    # pcap
    ap.add_argument("--pcap-out", help="Write PCAP path (mode=pcap-out)")
    ap.add_argument("--pcap-in", help="Read PCAP path (mode=replay)")
    ap.add_argument("--interface", help="Network interface for replay (en0, lo0, eth0, ...)")
    ap.add_argument("--randomize-payload", action="store_true")
    ap.add_argument("--randomize-size", nargs=2, type=int, metavar=("MIN","MAX"))
    ap.add_argument("--shuffle", action="store_true")
    ap.add_argument("--loop", type=int, default=1)

    args = ap.parse_args()

    if args.mode == "blast":
        if args.protocol == "udp":
            blast_udp(args.host, args.port, args.pps, args.payload, args.seconds)
        else:
            blast_tcp(args.host, args.port, args.pps, args.payload, args.seconds)

    elif args.mode == "pcap-out":
        if not args.pcap_out: sys.exit("Need --pcap-out")
        write_pcap(args.pcap_out, args.pps * args.seconds, args.payload, args.pps)

    elif args.mode == "replay":
        if not args.pcap_in or not args.interface:
            sys.exit("Need --pcap-in and --interface")
        size_rng = tuple(args.randomize_size) if args.randomize_size else None
        replay_pcap(args.pcap_in, args.interface,
                    randomize_payload=args.randomize_payload,
                    randomize_size=size_rng,
                    shuffle=args.shuffle,
                    loop=args.loop)

if __name__ == "__main__":
    main()
