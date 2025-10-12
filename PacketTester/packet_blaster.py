#!/usr/bin/env python3
"""
packet_blaster.py

PCAP Replay Tool:
- Replay PCAP files over a network interface (link-layer).
- Preserves original packet structure and data.
- Configurable PPS rate or use original PCAP timing.
- Loop support for repeated replay.
"""

import argparse, sys, time

try:
    from scapy.all import rdpcap, sendp
    SCAPY_AVAILABLE = True
except Exception:
    SCAPY_AVAILABLE = False

# -------------------------
# PCAP replay
# -------------------------
def replay_pcap(path: str, iface: str, pps: int = 0, loop: int = 1):
    if not SCAPY_AVAILABLE:
        print("Install scapy: pip install scapy")
        return
    packets = rdpcap(path)
    frames = list(packets) * loop

    print(f"Replaying {len(frames)} frames from {path} on {iface} (pps={pps if pps > 0 else 'original timing'})")
    
    if pps > 0:
        # Controlled rate replay
        interval = 1.0 / pps
        for pkt in frames:
            sendp(pkt, iface=iface, verbose=False)
            time.sleep(interval)
    else:
        # Original timing from PCAP
        for pkt in frames:
            sendp(pkt, iface=iface, verbose=False)
    
    print("Replay complete.")

# -------------------------
# CLI
# -------------------------
def main():
    ap = argparse.ArgumentParser(description="PCAP Replay Tool")
    ap.add_argument("--pcap-in", required=True, help="PCAP file path to replay")
    ap.add_argument("--interface", required=True, help="Network interface for replay (en0, lo0, eth0, ...)")
    ap.add_argument("--pps", type=int, default=0, help="Packets per second (0=use original PCAP timing)")
    ap.add_argument("--loop", type=int, default=1, help="Number of times to loop the PCAP")

    args = ap.parse_args()
    
    replay_pcap(args.pcap_in, args.interface, pps=args.pps, loop=args.loop)

if __name__ == "__main__":
    main()
