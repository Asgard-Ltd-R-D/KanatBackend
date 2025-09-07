#!/usr/bin/env python3
"""
Simple packet capture test to verify if LibPcap is working
"""
import socket
import time
import threading

def send_packets():
    """Send UDP packets to localhost"""
    print("Starting packet sender...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for i in range(10):
        message = f"Test packet {i}"
        sock.sendto(message.encode(), ('127.0.0.1', 54321))
        print(f"Sent: {message}")
        time.sleep(0.5)
    sock.close()
    print("Done sending packets")

def test_capture():
    """Test if we can capture packets using a simple approach"""
    try:
        from scapy.all import sniff, UDP, IP
        print("Testing packet capture with Scapy...")
        
        # Start packet sender in background
        sender_thread = threading.Thread(target=send_packets)
        sender_thread.start()
        
        # Capture packets
        packets = sniff(filter="udp and host 127.0.0.1", count=5, timeout=10)
        print(f"Captured {len(packets)} packets")
        
        for i, packet in enumerate(packets):
            print(f"Packet {i}: {packet.summary()}")
            
        sender_thread.join()
        
    except ImportError:
        print("Scapy not available, trying alternative...")
        # Try alternative approach
        send_packets()

if __name__ == "__main__":
    test_capture()
