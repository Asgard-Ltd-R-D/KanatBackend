import sys
try:
    from scapy.all import rdpcap, TCP
except ImportError:
    print("scapy not found")
    sys.exit(1)

packets = rdpcap('../motion_seq.pcap')
count = 0
for pkt in packets:
    if pkt.haslayer(TCP) and pkt[TCP].dport == 4949:
        payload = bytes(pkt[TCP].payload)
        if len(payload) > 7:
            # Parse Opcode (index 5, 6)
            # 0,1: Start
            # 2: Len
            # 3,4: Grp, Axis
            # 5,6: Opcode
            opcode = (payload[5] << 8) | payload[6]
            
            # Ignore GetLoadPosition (0x0109) and DG Group (0x0Fxx)
            if count >= 2155 and count <= 2165:
                 print(f"Packet {count} Opcode 0x{opcode:04X}: {payload.hex(' ')}")
            
            count += 1
            if count > 2170:
                break
