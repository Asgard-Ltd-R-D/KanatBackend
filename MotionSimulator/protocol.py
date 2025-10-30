# protocol.py
# Shared protocol constants and packet builder
import struct

# ===============================
# Version Information
# ===============================
__version__ = "1.2.0" # Added Axis ON/OFF/RESET, CMER, Ballistic Offset
__updated__ = "2025-10-25"

# ===============================
# Protocol Constants
# ===============================
START_BYTE_1 = 0x50
START_BYTE_2 = 0x54
ACK_REPLY = b'\x06'

# ===============================
# TCP OPCODES (Numerical Opcode to Name mapping)
# ===============================
OPCODES = {
    # Motion Data Request Opcodes
    0x0106: "MOT_GetMotorCurrent",
    0x0107: "MOT_GetMotorVoltage",
    0x0109: "MOT_GetLoadPosition",
    0x010A: "MOT_GetMotorSpeed",
    
    # Motion Control Opcodes
    0x0130: "MOT_SetAcceleration",
    0x0131: "MOT_SetSpeed",
    0x0134: "MOT_Update",
    0x0138: "MOT_SetPositionRelative",
    0x0139: "MOT_SetPositionAbsolute",
    0x013B: "MOT_SetPositionMode",
    
    # Axis Control Opcodes
    0x013C: "MOT_AxisOn",
    0x013D: "MOT_AxisOff",
    0x013E: "MOT_AxisReset",
    
    # Error Opcodes
    0x0E0B: "ERR_CaptureMotorErrorRegister", # CMER
    
    # LRF Opcodes (System Axis 0)
    0x0300: "LRF_SetRange",	
    0x0301: "LRF_GetRange",	
    
    # DG (Dual Gimbal/Mode Control) Opcodes
    0x0FA0: "DG_SetSyncMode",	
    0x0FA1: "DG_SetInnerMode",
    0x0FBE: "DG_GetBallisticOffset", 
    0x0FBD: "DG_SetBallisticOffset", 
    
    # Communication Opcodes (System Axis 0)
    0x0702: "COM_Connect",
}

# Create a reverse mapping (Name to Numerical Opcode)
NAME_TO_OPCODE = {name: opcode for opcode, name in OPCODES.items()}

# ===============================
# Packet Building
# ===============================

def calculate_checksum(packet_body):
    """Calculates the checksum for a given packet body."""
    return sum(packet_body) & 0xFF

def build_packet(group_id, axis_id, opcode, data=None):
    """Builds a standard command packet."""
    op_high = (opcode >> 8) & 0xFF
    op_low = opcode & 0xFF
    data = data or []
    # Length field = GroupID(1) + AxisID(1) + Opcode(2) + DataLength
    length = 1 + 1 + 2 + len(data)
    body = [length, group_id, axis_id, op_high, op_low] + data
    checksum = calculate_checksum(body)
    packet = [START_BYTE_1, START_BYTE_2] + body + [checksum]
    return bytearray(packet)

def build_reply_packet(group_id, axis_id, opcode, data=None):
    """Builds a reply packet (used by the server)."""
    return build_packet(group_id, axis_id, opcode, data)

# ===============================
# Packet Parsing
# ===============================

def parse_packet(buffer):
    """
    Parses a single packet from a buffer.
    Returns (packet, remaining_buffer) or (None, remaining_buffer)
    """
    start_index = buffer.find(bytes([START_BYTE_1, START_BYTE_2]))
    if start_index == -1:
        return None, b''

    buffer = buffer[start_index:]
    
    # Minimum possible packet length (no data) is 8 bytes.
    if len(buffer) < 8:
        return None, buffer

    length_from_header = buffer[2]
    # Total packet length = StartBytes(2) + Body(1+payload_len) + Checksum(1)
    # The Body consists of the length byte itself plus the payload.
    # So, Total Length = 2 + (1 + length_from_header) + 1 = 4 + length_from_header
    total_packet_len = 4 + length_from_header
    
    if len(buffer) < total_packet_len:
        return None, buffer

    packet = buffer[:total_packet_len]
    remaining_buffer = buffer[total_packet_len:]

    body = packet[2:-1]
    expected_cs = calculate_checksum(body)
    received_cs = packet[-1]
    
    if expected_cs != received_cs:
        print(f"[Parse] Checksum fail! Got {received_cs}, expected {expected_cs}. Packet: {packet.hex(' ')}")
        return None, remaining_buffer

    return packet, remaining_buffer

