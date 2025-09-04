using PacketProcessing.Entities.Packet;
using PacketProcessing.Utils.Parsers;
using Xunit;

namespace PacketProcessing.Tests.Unit.NetworkingTests;

/// <summary>
/// Tests for packet parsers to ensure they correctly parse binary packet data
/// </summary>
public class ParserTests
{
    [Fact]
    public void MotionPacketParser_ShouldParseValidTcpPacket()
    {
        Console.WriteLine("🔍 Testing Motion Packet TCP Parser");
        Console.WriteLine("===================================");
        
        // Arrange
        var packetData = CreateValidMotionTcpPacket();
        
        Console.WriteLine($"✓ Created TCP packet: {packetData.Length} bytes");
        
        // Act
        var parsedPacket = ParseMapper.Map<MotionPacketEntity>(packetData);
        
        Console.WriteLine("✓ Parsing completed");
        
        // Assert
        Assert.NotNull(parsedPacket);
        Assert.True(parsedPacket.Type);
        Assert.NotNull(parsedPacket.OpCode);
        Assert.NotNull(parsedPacket.OpCodeDescription);
        Assert.True(parsedPacket.Axis >= 0 && parsedPacket.Axis <= 5);
        Assert.NotNull(parsedPacket.FloatValue);
        
        Console.WriteLine($"✓ Parsed packet: Type={parsedPacket.Type}, OpCode={parsedPacket.OpCode}, Axis={parsedPacket.Axis}, FloatValue={parsedPacket.FloatValue}");
        Console.WriteLine("✅ Motion Packet TCP Parser Test PASSED!\n");
    }

    [Fact]
    public void SafetyPacketParser_ShouldParseValidUdpPacket()
    {
        Console.WriteLine("🔍 Testing Safety Packet UDP Parser");
        Console.WriteLine("===================================");
        
        // Arrange
        var packetData = CreateValidSafetyUdpPacket();
        
        Console.WriteLine($"✓ Created UDP packet: {packetData.Length} bytes");
        
        // Act
        var parsedPacket = ParseMapper.Map<SafetyPacketEntity>(packetData);
        
        Console.WriteLine("✓ Parsing completed");
        
        // Assert
        Assert.NotNull(parsedPacket);
        Assert.True(parsedPacket.Type);
        Assert.NotNull(parsedPacket.OpCode);
        Assert.NotNull(parsedPacket.OpCodeDescription);
        Assert.NotNull(parsedPacket.State);
        
        Console.WriteLine($"✓ Parsed packet: Type={parsedPacket.Type}, OpCode={parsedPacket.OpCode}, State={parsedPacket.State}");
        Console.WriteLine("✅ Safety Packet UDP Parser Test PASSED!\n");
    }

    [Fact]
    public void OnVifPacketParser_ShouldHandleHttpPacket()
    {
        Console.WriteLine("🔍 Testing OnVIF Packet HTTP Parser");
        Console.WriteLine("===================================");
        
        // Arrange
        var packetData = CreateValidOnVifHttpPacket();
        
        Console.WriteLine($"✓ Created HTTP packet: {packetData.Length} bytes");
        
        // Act
        var parsedPacket = ParseMapper.Map<OnVIFPacketEntity>(packetData);
        
        Console.WriteLine("✓ Parsing completed");
        
        // Assert
        Assert.NotNull(parsedPacket);
        Assert.True(parsedPacket.Type);
        Assert.NotNull(parsedPacket.Description);
        Assert.True(parsedPacket.Measurement >= 0);
        
        Console.WriteLine($"✓ Parsed packet: Type={parsedPacket.Type}, Description={parsedPacket.Description}, Measurement={parsedPacket.Measurement}");
        
        Console.WriteLine("✅ OnVIF Packet HTTP Parser Test PASSED!\n");
    }

    private byte[] CreateValidMotionTcpPacket()
    {
        var packet = new List<byte>();
        
        // Ethernet header (14 bytes)
        packet.AddRange(new byte[] { 0x00, 0x11, 0x22, 0x33, 0x44, 0x55 }); // Dest MAC
        packet.AddRange(new byte[] { 0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB }); // Src MAC
        packet.AddRange(new byte[] { 0x08, 0x00 }); // EtherType (IPv4)
        
        // IPv4 header (20 bytes)
        packet.Add(0x45); // Version (4) + IHL (5)
        packet.Add(0x00); // TOS
        packet.AddRange(BitConverter.GetBytes((ushort)60).Reverse().ToArray()); // Total Length
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Identification
        packet.AddRange(new byte[] { 0x40, 0x00 }); // Flags + Fragment Offset
        packet.Add(0x40); // TTL
        packet.Add(0x06); // Protocol (TCP)
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Header Checksum
        packet.AddRange(new byte[] { 192, 168, 1, 100 }); // Source IP
        packet.AddRange(new byte[] { 192, 168, 1, 200 }); // Destination IP
        
        // TCP header (20 bytes)
        packet.AddRange(BitConverter.GetBytes((ushort)12345).Reverse().ToArray()); // Source Port
        packet.AddRange(BitConverter.GetBytes((ushort)54321).Reverse().ToArray()); // Destination Port
        packet.AddRange(new byte[] { 0x00, 0x00, 0x00, 0x00 }); // Sequence Number
        packet.AddRange(new byte[] { 0x00, 0x00, 0x00, 0x00 }); // Acknowledgment Number
        packet.Add(0x50); // Data Offset (5) + Reserved
        packet.Add(0x18); // Flags (PSH + ACK)
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Window Size
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Checksum
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Urgent Pointer
        
        // CapTrack PDU
        packet.AddRange(new byte[] { 0xCA, 0xFE }); // StartByte
        packet.Add(8); // Length (GroupID + AxisID + OPCODE + DATA)
        packet.Add(1); // GroupID
        packet.Add(2); // AxisID
        // OPCODE (big-endian)
        var opcodeBe = BitConverter.GetBytes((ushort)0x0101);
        Array.Reverse(opcodeBe);
        packet.AddRange(opcodeBe);

        // DATA float (big-endian)
        var floatLe = BitConverter.GetBytes(42.5f);
        Array.Reverse(floatLe);
        packet.AddRange(floatLe);
        packet.Add(0xAB); // Checksum
        
        return packet.ToArray();
    }

    private byte[] CreateValidSafetyUdpPacket()
    {
        var packet = new List<byte>();
        
        // Ethernet header (14 bytes)
        packet.AddRange(new byte[] { 0x00, 0x11, 0x22, 0x33, 0x44, 0x55 }); // Dest MAC
        packet.AddRange(new byte[] { 0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB }); // Src MAC
        packet.AddRange(new byte[] { 0x08, 0x00 }); // EtherType (IPv4)
        
        // IPv4 header (20 bytes)
        packet.Add(0x45); // Version (4) + IHL (5)
        packet.Add(0x00); // TOS
        packet.AddRange(BitConverter.GetBytes((ushort)48).Reverse().ToArray()); // Total Length (IPv4 + UDP + PDU = 20 + 8 + 20 = 48)
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Identification
        packet.AddRange(new byte[] { 0x40, 0x00 }); // Flags + Fragment Offset
        packet.Add(0x40); // TTL
        packet.Add(0x11); // Protocol (UDP)
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Header Checksum
        packet.AddRange(new byte[] { 192, 168, 1, 100 }); // Source IP
        packet.AddRange(new byte[] { 132, 8, 7, 101 }); // Destination IP (PBE)
        
        // UDP header (8 bytes)
        packet.AddRange(BitConverter.GetBytes((ushort)12345).Reverse().ToArray()); // Source Port
        packet.AddRange(BitConverter.GetBytes((ushort)54321).Reverse().ToArray()); // Destination Port
        packet.AddRange(BitConverter.GetBytes((ushort)28).Reverse().ToArray()); // Length (UDP header + PDU)
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Checksum
        
        // Safety/Modbus-like PDU (20 bytes)
        packet.AddRange(new byte[] { 0x00, 0x01 }); // TID
        packet.AddRange(new byte[] { 0x00, 0x00 }); // PID
        packet.AddRange(new byte[] { 0x00, 0x0E }); // Length
        packet.Add(0x01); // UnitID
        packet.Add(0x06); // FunctionCode
        packet.AddRange(new byte[] { 0x00, 0x00 }); // param1
        packet.AddRange(new byte[] { 0x00, 0x00 }); // param2
        packet.AddRange(new byte[] { 0x00, 0x00 }); // param3
        packet.AddRange(new byte[] { 0x00, 0x00 }); // param4
        packet.AddRange(new byte[] { 0x00, 0x10 }); // DO (big-endian)
        packet.AddRange(new byte[] { 0xFF, 0x00 }); // STATE (big-endian)
        
        return packet.ToArray();
    }

    private byte[] CreateValidOnVifHttpPacket()
    {
        // Create a simple HTTP request with binary body
        var httpRequest = "POST /onvif/device_service HTTP/1.1\r\n" +
                         "Host: localhost\r\n" +
                         "Content-Type: application/soap+xml\r\n" +
                         "Content-Length: 8\r\n\r\n";
        
        var httpBytes = System.Text.Encoding.ASCII.GetBytes(httpRequest);
        var packet = new List<byte>();
        packet.AddRange(httpBytes);
        
        // Add binary data for OnVIF
        packet.AddRange(BitConverter.GetBytes(2.5f)); // Zoom
        packet.AddRange(BitConverter.GetBytes(150.0f)); // Measurement
        
        return packet.ToArray();
    }
}
