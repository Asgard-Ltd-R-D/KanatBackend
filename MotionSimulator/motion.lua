-- Define the protocol
CapTrack_proto = Proto("CapTrack", "CapTrack")
local fields = CapTrack_proto.fields

local e_opcode = {
    [0x0101] = "MOT_MerRegister",
    [0x0102] = "MOT_DerRegister",
    [0x0103] = "MOT_SrhRegister",
    [0x0104] = "MOT_SrlRegister",
    [0x0105] = "MOT_MsrRegister",
    [0x0106] = "MOT_GetMotorCurrent",
    [0x0107] = "MOT_GetMotorVoltage",
    [0x0108] = "MOT_GetMotorPosition",
    [0x0109] = "MOT_GetLoadPosition",
    [0x010A] = "MOT_GetMotorSpeed",
    [0x010C] = "MOT_GetNegSWLS",
    [0x010D] = "MOT_GetPosSWLS",
    [0x0110] = "MOT_IsActiveSWLS",
    [0x014F] = "MOT_GetShortPath",
    [0x012E] = "MOT_GetMaxCurrent",
    [0x0130] = "MOT_SetAcceleration",
    [0x0131] = "MOT_SetSpeed",
    [0x0132] = "MOT_SendPosition",
    [0x0133] = "MOT_SetActualPosition",
    [0x0134] = "MOT_Update",
    [0x0135] = "MOT_Homing",
    [0x0136] = "MOT_SetNegSWLS",
    [0x0137] = "MOT_SetPosSWLS",
    [0x0146] = "MOT_ActivateSWLS",
    [0x0138] = "MOT_SetPositionRelative",
    [0x0139] = "MOT_SetPositionAbsolute",
    [0x013A] = "MOT_SetSpeedMode",
    [0x013B] = "MOT_SetPositionMode",
    [0x013C] = "MOT_AxisOn",
    [0x013D] = "MOT_AxisOff",
    [0x013E] = "MOT_AxisReset",
    [0x013F] = "MOT_SetTum",
    [0x0143] = "MOT_ResetFaults",
    [0x014E] = "MOT_SetShortPath",
    [0x0165] = "MOT_SaveMotorSetting",
    [0x0166] = "MOT_SetMaxCurrent",
    [0x0144] = "MOT_SetMotionComplete",
	
    [0x0400] = "SCN_SetYawMin",
    [0x0401] = "SCN_SetYawMax",
    [0x0402] = "SCN_SetPitchMin",
    [0x0403] = "SCN_SetNumSteps",
    [0x0404] = "SCN_SetStepHeight",
    [0x0405] = "SCN_SetScanSpeed",
    [0x0406] = "SCN_SetShortPath",
    [0x0407] = "SCN_IsScanOn",
    [0x0408] = "SCN_StopScan",
    [0x040C] = "SCN_StartScanZigZag",
    [0x040D] = "SCN_StartScanSnake",
    [0x040E] = "SCN_StartScanSquare",
	
    [0x0700] = "COM_Reboot",
    [0x0702] = "COM_Connect",
    [0x0703] = "COM_Disconnect",
    [0x0704] = "COM_IsConnected",
    [0x0705] = "COM_StartKeepAlive",
    [0x0706] = "COM_IsKeepAliveOn",
    [0x0708] = "COM_setKeepAliveTimeout",
    [0x0709] = "COM_getKeepAliveTimeout",
    [0x071C] = "COM_setKeepAliveCount",
    [0x071D] = "COM_getKeepAliveCount",
    [0x0719] = "COM_SetComType",
    [0x0713] = "COM_SysState",
	
	[0x0800] = "STB_StabilizationOn",
	[0x0801] = "STB_StabilizationOff",
	[0x0822] = "STB_GetStabError",
	[0x0839] = "STB_SetStabMinAccel",
	[0x083A] = "STB_GetStabMinAccel",
	[0x0D04] = "STB_SetSpdKp",	
	[0x0D08] = "STB_GetSpdKp",	
	[0x0D05] = "STB_SetSpdKi",	
	[0x0D09] = "STB_GetSpdKi",	
	[0x0D06] = "STB_SetSpdKd",	
	[0x0D0A] = "STB_GetSpdKd",	
	[0x0D16] = "STB_SetPosKp",	
	[0x0D17] = "STB_GetPosKp",	
	[0x0D18] = "STB_SetPosKi",	
	[0x0D19] = "STB_GetPosKi",	
	[0x0D1A] = "STB_SetPosKd",	
	[0x0D1B] = "STB_GetPosKd",	
	[0x082B] = "STB_SetDistanceToTarget",	
	[0x082A] = "STB_GetDistanceToTarget",	
	[0x0825] = "STB_SetCentralAxes",	
	[0x0826] = "STB_GetCentralAxes",	
	[0x0C76] = "STB_SetRollCompensation",	
	[0x0C77] = "STB_GetRollCompensation",	
	[0x084F] = "STB_SetRebalanceOn",	
	[0x0850] = "STB_GetRebalanceOn",	
	[0x0851] = "STB_GetRebalanceStatus",	
	[0x0D07] = "STB_SaveStabilizationCfg",	

	[0x0FA0] = "DG_SetSyncMode",	
	[0x0FA1] = "DG_SetInnerMode",	
	[0x0FA2] = "DG_IsSyncMode",	
	[0x0FA3] = "DG_IsInnerMode",	
	[0x0FA5] = "DG_GetPosDiff",	
	[0x0FA6] = "DG_SetMaxDiff",	
	[0x0FA7] = "DG_GetMaxDiff",	
	[0x0FA9] = "DG_GoToCamera",	
	[0x0FAA] = "DG_SetSyncSpd",	
	[0x0FAB] = "DG_SetMainGimbal",	
	[0x0FAC] = "DG_GetMainGimbal",	
	[0x0FB0] = "DG_CTC",	
	[0x0FB1] = "DG_GetCTCoffset",	
	[0x0FB2] = "DG_ResetCTCoffset",	
	[0x0FB5] = "DG_GetSyncSpd",	
	[0x0FB6] = "DG_SetActiveWeapon",	
	[0x0FB7] = "DG_GetActiveWeapon",	
	[0x0FBA] = "DG_SetActiveCamera",	
	[0x0FBB] = "DG_GetActiveCamera",	
	[0x0FB9] = "DG_IsBoresightEn",	
	[0x0FBC] = "DG_GetBoresightOffset",	
	[0x0FBD] = "DG_SetBallisticOffset",	
	[0x0FBE] = "DG_GetBallisticOffset",	
	[0x0FBF] = "DG_GetSafetyStatus",	
	[0x0FC0] = "DG_GetLoadStatus",	
	[0x0FC1] = "DG_GetCapsnapIOStatus",	
	[0x0FC2] = "DG_GetNumBullets",	
	[0x0FC3] = "DG_ResetNumBullets",	
	[0x0FC4] = "DG_IsCapSnapReady",	
	
	[0x0300] = "LRF_SetRange",	
	[0x0301] = "LRF_GetRange",	
	
    [0x0C2D] = "COM_GetPn",
    [0x0C2F] = "COM_GetSn",
    [0x0C4A] = "COM_GetFw",
    [0x0C4C] = "COM_GetHw",
	
	[0x0E01] = "ERR_CaptureSystemRegister",
	[0x0E02] = "ERR_ClearErrors",
	[0x0E03] = "ERR_GetDriverErrorString",
	[0x0E04] = "ERR_GetSystemErrorString",
	[0x0E05] = "ERR_GetLoadImuErrorString",
	[0x0E06] = "ERR_GetBaseImuErrorString",
	[0x0E07] = "ERR_GetGpsComErrorString",
	[0x0E08] = "ERR_GetGpsPosString",
	[0x0E09] = "ERR_GetGpsHeadErrorString",
	[0x0E0A] = "ERR_GetProtocolErrorString",
	[0x0E0D] = "ERR_GetAbsEncComErrorString",
	[0x0E0E] = "ERR_GetAbsEncCRCErrorString",
	[0x0E0F] = "ERR_GetBodyImuErrorString",
	[0x0E10] = "ERR_GetHomingErrorString",
	[0x0E12] = "ERR_OperationRegister",

    [0x070A] = "IP_SetControllerIP",
    [0x070D] = "IP_GetControllerIP",
    [0x070B] = "IP_SetControllerPort",
    [0x070E] = "IP_GetControllerPort",
    [0x071A] = "IP_SetControllerSubnetMask",
    [0x070B] = "IP_GetControllerSubnetMask",
    [0x0710] = "IP_SaveIP",

}

-- Define fields
fields.StartByte = ProtoField.uint16("StartByte", "StartByte", base.HEX)
fields.Length = ProtoField.uint8("Length", "Length", base.DEC)
fields.GroupID = ProtoField.uint8("GroupID", "GroupID")
fields.AxisID = ProtoField.uint8("AxisID", "AxisID", base.DEC)
fields.OPCODE = ProtoField.uint16("OPCODE", "OPCODE", base.HEX)
fields.OPCODE_DESCR = ProtoField.uint16("OPCODE_DESCR", "OPCODE_DESCR", base.HEX, e_opcode)
fields.DATA = ProtoField.bytes("DATA", "DATA")
fields.FloatValue = ProtoField.float("FloatValue", "FloatValue")
fields.AckNack = ProtoField.uint8("AckNack", "AckNack")
fields.CS = ProtoField.uint8("CS", "CS", base.HEX)


-- Custom implementation of math.ldexp for Lua 5.1
local function ldexp(fraction, exponent)
    return fraction * (2 ^ exponent)
end

-- Helper function to convert HEX to float
local function hex_to_float(hex)
    local sign = (hex & 0x80000000 == 0) and 1 or -1
    local exponent = ((hex >> 23) & 0xFF) - 127
    local fraction = (hex & 0x007FFFFF) / 0x00800000
    return sign * ldexp(fraction, exponent)  -- Use custom ldexp function
end


-- Dissector function
function CapTrack_proto.dissector(buffer, pinfo, tree)
    -- Set protocol column
    pinfo.cols.protocol = "CapTrack"

    -- Identify protocol type based on ports
    local src_port = pinfo.src_port
    local dst_port = pinfo.dst_port
    local protocol_name = (src_port == 4949) and "MOTION_RPT" or (dst_port == 4949) and "HOST_CMD" or "CapTrack"
    pinfo.cols.protocol = protocol_name

    -- Create protocol subtree
    local subtree = tree:add(CapTrack_proto, buffer(), "CapTrack")

    -- Parse fields
    subtree:add(fields.StartByte, buffer(0, 2))
    local length_value = buffer(2, 1):uint()
    subtree:add(fields.Length, buffer(2, 1))
    subtree:add(fields.GroupID, buffer(3, 1))
    subtree:add(fields.AxisID, buffer(4, 1))
    subtree:add(fields.OPCODE, buffer(5, 2))
    subtree:add(fields.OPCODE_DESCR, buffer(5, 2))

    -- Handle dynamic DATA bytes based on LENGTH
    local data_length = length_value - 4
    if data_length > 0 then
        local data_buffer = buffer(7, data_length)
        if data_length % 4 == 0 then -- Ensure it aligns with float conversion
            -- Convert and collect float values
            local float_values = {}
            for offset = 0, data_length - 1, 4 do
                local hex_value = data_buffer(offset, 4):le_uint()
                local float_value = hex_to_float(hex_value)
                table.insert(float_values, float_value)
            end
            subtree:add(fields.FloatValue, data_buffer):append_text("[" .. data_buffer:bytes():tohex() .. "]")
        else
            -- Handle non-float data as needed
        end
    end

    subtree:add(fields.CS, buffer(7 + data_length, 1))
end

-- Register the dissector
local tcp_table = DissectorTable.get("tcp.port")
tcp_table:add(4949, CapTrack_proto)