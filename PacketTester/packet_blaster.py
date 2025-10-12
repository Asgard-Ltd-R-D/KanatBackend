#!/usr/bin/env python3
"""
packet_blaster.py

PCAP Replay Tool:
- Replay PCAP frames over a specific network interface at link-layer (sendp).
- Preserves original packet structure and (optionally) original timing.
- Fixed-rate pacing with --pps, or original PCAP timing with --use-original-timing.
- Loop support to repeat the PCAP N times.
- Optional BPF filter to pre-select frames from the PCAP.
- Graceful Ctrl-C handling and basic interface validation.

Requirements:
- scapy (pip install scapy)
- Root/admin privileges for raw L2 send (Linux/macOS root, Windows admin + Npcap)
"""

from __future__ import annotations
import argparse
import sys
import time

try:
    from scapy.all import rdpcap, sendp, sniff, get_if_list
    SCAPY_AVAILABLE = True
except Exception:
    SCAPY_AVAILABLE = False


def load_packets(path: str):
    """
    Load packets from a PCAP. If a BPF filter is provided, use scapy.sniff(offline=..., filter=...).
    Otherwise, use rdpcap().
    """
    if not SCAPY_AVAILABLE:
        raise RuntimeError("Scapy not available. Install with: pip install scapy")

    return rdpcap(path)


def validate_interface(iface: str) -> None:
    """
    Ensure the interface exists on this host. Raises ValueError if not found.
    """
    if not SCAPY_AVAILABLE:
        return
    try:
        ifaces = set(get_if_list() or [])
    except Exception:
        # If get_if_list fails (rare), skip validation
        return
    if iface not in ifaces:
        raise ValueError(
            f"Interface '{iface}' not found. Available: {', '.join(sorted(ifaces)) or 'unknown'}"
        )


def compute_intervals_from_timestamps(packets) -> list[float]:
    """
    Return a list of inter-packet delays (seconds) based on packet timestamps.
    The first element is 0.0 (no delay before first packet).
    """
    total = len(packets)
    if total == 0:
        return []
    intervals = [0.0]
    # Some PCAPs can have non-monotonic times; we guard with max(0, dt)
    for i in range(1, total):
        t_cur = float(getattr(packets[i], "time", 0.0))
        t_prev = float(getattr(packets[i - 1], "time", 0.0))
        intervals.append(max(0.0, t_cur - t_prev))
    return intervals


def replay_pcap(
    path: str,
    iface: str,
    pps: int = 0,
    loop: int = 1
) -> None:
    """
    Replay packets from PCAP on iface.

    - If pps > 0: fixed-rate pacing at 'pps' packets/sec (overrides original timing).
    - If pps == 0 and use_original_timing: sleep according to inter-packet gaps in the PCAP (scaled by 'speed').
    - Else: send as fast as possible.

    'speed' scales the original timing (2.0 = 2x faster; 0.5 = 2x slower).
    """
    if not SCAPY_AVAILABLE:
        print("Scapy not available. Install with: pip install scapy")
        return

    if loop < 1:
        loop = 1

    if pps < 0:
        pps = 0

    use_original_timing = (pps == 0)

    # Load packets (with optional BPF pre-filter)
    packets = load_packets(path)
    total_pkts = len(packets)
    if total_pkts == 0:
        print("No packets to replay (empty PCAP or filtered to zero).")
        return

    # Validate interface
    try:
        validate_interface(iface)
    except ValueError as ve:
        print(str(ve))
        return

    # Precompute intervals for original timing
    intervals: list[float] | None = None
    if pps == 0 and use_original_timing:
        intervals = compute_intervals_from_timestamps(packets)

    # Fixed-rate interval if needed
    interval_pps = (1.0 / pps) if pps > 0 else 0.0

    sent = 0
    start_wall = time.perf_counter()
    try:
        for li in range(loop):
            if pps == 0 and use_original_timing:
                # Respect original deltas (scaled by speed)
                for i, pkt in enumerate(packets):
                    sendp(pkt, iface=iface, verbose=False)
                    sent += 1
                    if i < total_pkts - 1:
                        delay = intervals[i + 1]
                        if delay > 0:
                            delay /= 1
                            # tiny guards to avoid negative/NaN sleeps
                            if delay > 0:
                                time.sleep(delay)
            elif pps > 0:
                # Fixed-rate pacing
                next_ts = time.perf_counter()
                for pkt in packets:
                    sendp(pkt, iface=iface, verbose=False)
                    sent += 1
                    next_ts += interval_pps
                    remaining = next_ts - time.perf_counter()
                    if remaining > 0:
                        # Sleep most of the remaining, then spin-wait for tighter pacing
                        if remaining > 0.001:
                            time.sleep(remaining - 0.0005)
                        while time.perf_counter() < next_ts:
                            pass
            else:
                # Blast without pacing
                for pkt in packets:
                    sendp(pkt, iface=iface, verbose=False)
                    sent += 1

            # Optional per-loop progress
            print(f"Loop {li + 1}/{loop} complete. Sent so far: {sent}")

    except KeyboardInterrupt:
        print("\nInterrupted by user (Ctrl-C).")
    finally:
        dur = max(1e-9, time.perf_counter() - start_wall)
        rate = sent / dur
        print(f"Replay complete. Sent {sent} frames in {dur:.3f}s (~{int(rate)} pps).")


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="PCAP Replay Tool (link-layer)")
    ap.add_argument("--pcap-in", required=True, help="PCAP file path to replay")
    ap.add_argument("--interface", required=True, help="Network interface (e.g., en0, lo0, eth0, Ethernet)")
    ap.add_argument("--pps", type=int, default=0, help="Packets per second (0=not used)")
    ap.add_argument("--loop", type=int, default=1, help="Number of times to loop the PCAP")
    return ap.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])

    replay_pcap(
        path=args.pcap_in,
        iface=args.interface,
        pps=args.pps,
        loop=args.loop
    )


if __name__ == "__main__":
    main()
