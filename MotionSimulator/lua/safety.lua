-- Wireshark Lua dissector for SAFETY Modbus over UDP

-- Create a new dissector
local safety_proto = Proto("safety", "SAFETY Modbus")

-- Define the DO mappings

local DO_PBE = {
    [0x0010] = "1",
    [0x0027] = "DO3_FIRE1",
    [0x0012] = "DO2_MOTION",
    [0x0014] = "DO4_LED_FIRE_EN"

}

local DO_SBE = {
    [0x0010] = "DO0_RLD",
    [0x0011] = "DO1_RLD_SFTY",
    [0x0012] = "DO2_PWR",
    [0x0028] = "DO4_FIRE2",
    [0x0015] = "X5"
}


-- Define the state mapping
local state = {
    [0x0000] = "OFF",
    [0xff00] = "ON",
	[0x0001] = "PULSE",
	[0x0003] = "BURST",
	
}

-- Define the protocol fields
local fields = safety_proto.fields

fields.transaction_id = ProtoField.uint16("safety.transaction_id", "Transaction ID", base.HEX)
fields.protocol_id = ProtoField.uint16("safety.protocol_id", "Protocol ID", base.HEX)
fields.length = ProtoField.uint16("safety.length", "Length", base.DEC)
fields.unit_id = ProtoField.uint8("safety.unit_id", "Unit ID", base.DEC)
fields.function_code = ProtoField.uint8("safety.function_code", "Function Code", base.HEX)
fields.data = ProtoField.bytes("safety.data", "Data")
fields.param1 = ProtoField.uint16("safety.param1", "PARAM1", base.HEX)
fields.param2 = ProtoField.uint16("safety.param2", "PARAM2", base.HEX)
fields.param3 = ProtoField.uint16("safety.param3", "PARAM3", base.HEX)
fields.param4 = ProtoField.uint16("safety.param4", "PARAM4", base.HEX)
fields.DO = ProtoField.uint16("safety.DO", "DO", base.HEX)
fields.STATE = ProtoField.uint16("safety.STATE", "STATE", base.HEX, state)

-- Helper function to validate and add fields
local function add_field_safe(subtree, field, buffer, offset, length)
    if buffer:len() >= offset + length then
        subtree:add(field, buffer(offset, length))
    else
        subtree:add_expert_info(PI_MALFORMED, PI_ERROR, "Field length insufficient: Expected " .. length .. ", Available: " .. (buffer:len() - offset))
    end
end

-- Function to dynamically select the DO mapping based on the destination IP
local function get_do_mapping(dst_ip)
    if dst_ip == "132.8.7.101" then
        return DO_PBE
    elseif dst_ip == "132.8.7.102" then
        return DO_SBE
    else
        return nil
    end
end



-- Dissector function
function safety_proto.dissector(buffer, pinfo, tree)
    -- Ensure packet is long enough
    if not buffer or buffer:len() < 8 then return end

    -- Determine protocol and DO mapping based on destination IP
    local dst_ip = tostring(pinfo.dst)
    local do_mapping = get_do_mapping(dst_ip)

    if dst_ip == "132.8.7.101" then
        pinfo.cols.protocol = "PBE_CMD"
    elseif dst_ip == "132.8.7.102" then
        pinfo.cols.protocol = "SBE_CMD"
    else
        pinfo.cols.protocol = "SAFETY"
    end

    -- Add protocol to the dissection tree
    local subtree = tree:add(safety_proto, buffer())
    subtree:set_text("SAFETY Modbus Data")

    -- Create a new subtree for HEADER fields
    local header_subtree = subtree:add(safety_proto, buffer())
    header_subtree:set_text("HEADER")

    -- Parse fixed fields under HEADER subtree
    add_field_safe(header_subtree, fields.transaction_id, buffer, 0, 2)
    add_field_safe(header_subtree, fields.protocol_id, buffer, 2, 2)
    add_field_safe(header_subtree, fields.length, buffer, 4, 2)
    add_field_safe(header_subtree, fields.unit_id, buffer, 6, 1)

    -- Parse function code
    local function_code = buffer(7, 1):uint()
    add_field_safe(header_subtree, fields.function_code, buffer, 7, 1)

    -- Parse data field dynamically based on length field
    local length_field = buffer(4, 2):uint()
    local data_length = math.min(length_field - 2, buffer:len() - 8)

    if data_length > 0 then
        local data_subtree = subtree:add(fields.data, buffer(8, data_length))
        data_subtree:set_text("Data Field")

        add_field_safe(data_subtree, fields.param1, buffer, 8, 2)
        add_field_safe(data_subtree, fields.param2, buffer, 10, 2)
        add_field_safe(data_subtree, fields.param3, buffer, 12, 2)
        add_field_safe(data_subtree, fields.param4, buffer, 14, 2)

        if do_mapping then
            local do_value = buffer(16, 2):uint()
            data_subtree:add(fields.DO, buffer(16, 2)):append_text(" (" .. (do_mapping[do_value] or "Unknown") .. ")")
        end

        add_field_safe(data_subtree, fields.STATE, buffer, 18, 2)
    else
        subtree:add_expert_info(PI_MALFORMED, PI_ERROR, "Data field length is insufficient. Available: " .. data_length)
    end

    -- Handle specific function codes
  --  handle_function_code(function_code, buffer, subtree)
end

-- Register dissector to a specific UDP port (e.g., port 1025)
local udp_table = DissectorTable.get("udp.port")
udp_table:add(1025, safety_proto)
