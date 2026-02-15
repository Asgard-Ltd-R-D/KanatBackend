# protocol.py
# Shared protocol constants and packet builder
import struct

# ===============================
# Version Information
# ===============================
__version__ = "1.5.0" # Added full Opcode support
__updated__ = "2026-02-02"

# ===============================
# Protocol Constants
# ===============================
START_BYTE_1 = 0x50
START_BYTE_2 = 0x54
ACK_REPLY = b'\x06'

# ===============================
# TCP OPCODES (Numerical Opcode to Name mapping, grouped by ID)
# ===============================
OPCODES = {
    # --- Motion Opcodes (0x01xx) ---
    0x0106: "MOT_GetMotorCurrent",
    0x0107: "MOT_GetMotorVoltage",
    0x0108: "MOT_GetMotorPosition",
    0x0109: "MOT_GetLoadPosition",
    0x010A: "MOT_GetMotorSpeed",
    
    0x0101: "MOT_MerRegister",
    0x0102: "MOT_DerRegister",
    0x0103: "MOT_SrhRegister",
    0x0104: "MOT_SrlRegister",
    0x0105: "MOT_MsrRegister",
    0x010C: "MOT_GetNegSWLS",
    0x010D: "MOT_GetPosSWLS",
    0x0110: "MOT_IsActiveSWLS",
    0x014F: "MOT_GetShortPath",
    0x012E: "MOT_GetMaxCurrent",
    0x0130: "MOT_SetAcceleration",
    0x0131: "MOT_SetSpeed",
    0x0132: "MOT_SendPosition",
    0x0133: "MOT_SetActualPosition",
    0x0134: "MOT_Update",
    0x0135: "MOT_Homing",
    0x0136: "MOT_SetNegSWLS",
    0x0137: "MOT_SetPosSWLS",
    0x0146: "MOT_ActivateSWLS",
    0x0138: "MOT_SetPositionRelative",
    0x0139: "MOT_SetPositionAbsolute",
    0x013A: "MOT_SetSpeedMode",
    0x013B: "MOT_SetPositionMode",
    0x013C: "MOT_AxisOn",
    0x013D: "MOT_AxisOff",
    0x013E: "MOT_AxisReset",
    0x013F: "MOT_SetTum",
    0x0143: "MOT_ResetFaults",
    0x014E: "MOT_SetShortPath",
    0x0165: "MOT_SaveMotorSetting",
    0x0166: "MOT_SetMaxCurrent",
    0x0144: "MOT_SetMotionComplete",

    # --- SCAN commands (0x04xx) ---
    0x0400: "SCN_SetYawMin",
    0x0401: "SCN_SetYawMax",
    0x0402: "SCN_SetPitchMin",
    0x0403: "SCN_SetNumSteps",
    0x0404: "SCN_SetStepHeight",
    0x0405: "SCN_SetScanSpeed",
    0x0406: "SCN_SetShortPath",
    0x0407: "SCN_IsScanOn",
    0x0408: "SCN_StopScan",
    0x040C: "SCN_StartScanZigZag",
    0x040D: "SCN_StartScanSnake",
    0x040E: "SCN_StartScanSquare",

    # --- Communication Opcodes (0x07xx) ---
    0x0700: "COM_Reboot",
    0x0702: "COM_Connect",
    0x0703: "COM_Disconnect",
    0x0704: "COM_IsConnected",
    0x0705: "COM_StartKeepAlive",
    0x0706: "COM_IsKeepAliveOn",
    0x0708: "COM_setKeepAliveTimeout",
    0x0709: "COM_getKeepAliveTimeout",
    0x071C: "COM_setKeepAliveCount",
    0x071D: "COM_getKeepAliveCount",
    0x0719: "COM_SetComType",
    0x0713: "COM_SysState",

    # --- IP Config ---
    0x070A: "IP_SetControllerIP",
    0x070D: "IP_GetControllerIP",
    0x070B: "IP_SetControllerPort",
    0x070E: "IP_GetControllerPort",
    0x071A: "IP_SetControllerSubnetMask",
    0x0710: "IP_SaveIP",

    # --- Device Info ---
    0x0C2D: "COM_GetPn",
    0x0C2F: "COM_GetSn",
    0x0C4A: "COM_GetFw",
    0x0C4C: "COM_GetHw",

    # --- LRF Opcodes (0x03xx) ---
    0x0300: "LRF_SetRange",
    0x0301: "LRF_GetRange",
    
    # --- Stabilization (0x08xx / 0x0Dxx) ---
    0x0800: "STB_StabilizationOn",
    0x0801: "STB_StabilizationOff",
    0x0822: "STB_GetStabError",
    0x0839: "STB_SetStabMinAccel",
    0x083A: "STB_GetStabMinAccel",
    0x0D04: "STB_SetSpdKp",
    0x0D08: "STB_GetSpdKp",
    0x0D05: "STB_SetSpdKi",
    0x0D09: "STB_GetSpdKi",
    0x0D06: "STB_SetSpdKd",
    0x0D0A: "STB_GetSpdKd",
    0x0D16: "STB_SetPosKp",
    0x0D17: "STB_GetPosKp",
    0x0D18: "STB_SetPosKi",
    0x0D19: "STB_GetPosKi",
    0x0D1A: "STB_SetPosKd",
    0x0D1B: "STB_GetPosKd",
    0x082B: "STB_SetDistanceToTarget",
    0x082A: "STB_GetDistanceToTarget",
    0x0825: "STB_SetCentralAxes",
    0x0826: "STB_GetCentralAxes",
    0x0C76: "STB_SetRollCompensation",
    0x0C77: "STB_GetRollCompensation",
    0x084F: "STB_SetRebalanceOn",
    0x0850: "STB_GetRebalanceOn",
    0x0851: "STB_GetRebalanceStatus",
    0x0D07: "STB_SaveStabilizationCfg",

    # --- Error Opcodes (0x0Exx) ---
    0x0E0B: "ERR_CaptureMotorErrorRegister", 
    0x0E01: "ERR_CaptureSystemRegister",
    0x0E02: "ERR_ClearErrors",
    0x0E03: "ERR_GetDriverErrorString",
    0x0E04: "ERR_GetSystemErrorString",
    0x0E05: "ERR_GetLoadImuErrorString",
    0x0E06: "ERR_GetBaseImuErrorString",
    0x0E07: "ERR_GetGpsComErrorString",
    0x0E08: "ERR_GetGpsPosString",
    0x0E09: "ERR_GetGpsHeadErrorString",
    0x0E0A: "ERR_GetProtocolErrorString",
    0x0E0D: "ERR_GetAbsEncComErrorString",
    0x0E0E: "ERR_GetAbsEncCRCErrorString",
    0x0E0F: "ERR_GetBodyImuErrorString",
    0x0E10: "ERR_GetHomingErrorString",
    0x0E12: "ERR_OperationRegister",

    # --- Dual Gimbal/Mode Opcodes (0x0Fxx) ---
    0x0FA0: "DG_SetSyncMode",
    0x0FA1: "DG_SetInnerMode",
    0x0FA2: "DG_IsSyncMode",
    0x0FA3: "DG_IsInnerMode",
    0x0FA5: "DG_GetPosDiff",
    0x0FA6: "DG_SetMaxDiff",
    0x0FA7: "DG_GetMaxDiff",
    0x0FA9: "DG_GoToCamera",
    0x0FAA: "DG_SetSyncSpd",
    0x0FAB: "DG_SetMainGimbal",
    0x0FAC: "DG_GetMainGimbal",
    0x0FB0: "DG_CTC",
    0x0FB1: "DG_GetCTCoffset",
    0x0FB2: "DG_ResetCTCoffset",
    0x0FB5: "DG_GetSyncSpd",
    0x0FB6: "DG_SetActiveWeapon",
    0x0FB7: "DG_GetActiveWeapon",
    0x0FB9: "DG_IsBoresightEn",
    0x0FBA: "DG_SetActiveCamera",
    0x0FBB: "DG_GetActiveCamera",
    0x0FBC: "DG_GetBoresightOffset",
    0x0FBD: "DG_SetBallisticOffset",
    0x0FBE: "DG_GetBallisticOffset",
    0x0FBF: "DG_GetSafetyStatus",
    0x0FC0: "DG_GetLoadStatus",
    0x0FC1: "DG_GetCapsnapIOStatus",
    0x0FC2: "DG_GetNumBullets",
    0x0FC3: "DG_ResetNumBullets",
    0x0FC4: "DG_IsCapSnapReady",
}

# Create a reverse mapping (Name to Numerical Opcode)
NAME_TO_OPCODE = {name: opcode for opcode, name in OPCODES.items()}

# ===============================
# Packet Building
# ===============================

def calculate_checksum(packet_body):
    """Calculates the checksum for a given packet body."""
    # Sum is modulo 256 (0xFF)
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
        # No start bytes found, discard buffer
        return None, b''

    buffer = buffer[start_index:]
    
    # Minimum possible packet length (no data) is 8 bytes.
    if len(buffer) < 8:
        return None, buffer

    length_from_header = buffer[2]
    # Total packet length = StartBytes(2) + LengthByte(1) + Body(LengthValue) + Checksum(1)
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
