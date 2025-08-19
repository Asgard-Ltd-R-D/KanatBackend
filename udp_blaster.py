# udp_blaster.py
import argparse, socket, time, os, struct

def blast(host: str, port: int, pps: int, payload_size: int, seconds: int):
    """
    Sends UDP packets at ~pps using 10ms ticks (pps/100 per tick).
    Example: pps=10_000 -> 100 packets every 10ms.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = os.urandom(payload_size)

    tick_hz = 100                       # 100 ticks/sec -> 10ms per tick
    pkts_per_tick = max(1, pps // tick_hz)
    tick_interval = 1.0 / tick_hz

    end_time = time.perf_counter() + seconds
    next_tick = time.perf_counter()
    sent_total = 0

    print(f"Blasting to {host}:{port} at ~{pps} pps, payload={payload_size} bytes, duration={seconds}s")
    while time.perf_counter() < end_time:
        # send a burst for this tick
        for _ in range(pkts_per_tick):
            # (optional) include a counter in first 8 bytes to help validation
            counter = sent_total & 0xFFFFFFFFFFFFFFFF
            buf = struct.pack(">Q", counter) + payload[8:] if payload_size >= 8 else payload
            try:
                sock.sendto(buf, (host, port))
                sent_total += 1  # count only on successful send
            except OSError:
                # skip increment on failure; continue trying
                pass
        next_tick += tick_interval
        # coarse sleep; then spin if needed
        now = time.perf_counter()
        sleep_s = next_tick - now
        if sleep_s > 0.002:            # coarse sleep for >=2ms
            time.sleep(sleep_s - 0.001)
        while time.perf_counter() < next_tick:
            pass
    print(f"Done. Sent {sent_total} packets.")

def write_pcap(path: str, packets: int, payload_size: int, pps: int):
    """
    Writes a minimal PCAP with Ethernet/IP/UDP-like payload timing (no real headers).
    For *timing tests* in readers that honor per-packet timestamps.
    """
    try:
        from scapy.all import wrpcap, Raw, Ether
    except Exception:
        print("Scapy not installed. `pip install scapy` to use --pcap-out.")
        return

    print(f"Writing PCAP: {path} packets={packets} payload={payload_size} pps={pps}")
    pkt = Ether()/Raw(os.urandom(payload_size))
    # wrpcap can accept (pkt, ts) tuples to set timestamps
    t0 = time.time()
    dt = 1.0 / pps
    frames = []
    for i in range(packets):
        frames.append((pkt, t0 + i * dt))
    wrpcap(path, frames)
    print(f"PCAP written: {path}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--pps", type=int, default=10_000)
    ap.add_argument("--payload", type=int, default=256)
    ap.add_argument("--seconds", type=int, default=10)
    ap.add_argument("--pcap-out", default=None, help="Write a PCAP (offline) instead of blasting live")
    args = ap.parse_args()

    if args.pcap_out:
        write_pcap(args.pcap_out, packets=args.pps * args.seconds, payload_size=args.payload, pps=args.pps)
    else:
        blast(args.host, args.port, args.pps, args.payload, args.seconds)
