using System.Net;
using System.Net.Sockets;
using System.Text;
using Microsoft.Extensions.Logging;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Tests.CaptureServicesTests;

/// <summary>
/// Utility class for blasting packets to test capture services
/// </summary>
public class PacketBlaster : IDisposable
{
    private readonly ILogger<PacketBlaster> _logger;
    private readonly UdpClient _udpClient;
    private readonly TcpClient _tcpClient;
    private readonly HttpClient _httpClient;
    private bool _disposed;

    public PacketBlaster(ILogger<PacketBlaster> logger)
    {
        _logger = logger;
        _udpClient = new UdpClient();
        _tcpClient = new TcpClient();
        _httpClient = new HttpClient();
    }

    /// <summary>
    /// Sends a motion packet via UDP
    /// </summary>
    public async Task SendMotionPacketAsync(string targetIp, int port, MotionPacketEntity packet)
    {
        try
        {
            var jsonPayload = CreateMotionPacketJson(packet);
            var data = Encoding.UTF8.GetBytes(jsonPayload);
            
            var endpoint = new IPEndPoint(IPAddress.Parse(targetIp), port);
            await _udpClient.SendAsync(data, data.Length, endpoint);
            
            _logger.LogInformation("Sent motion packet to {TargetIp}:{Port} - {Payload}", targetIp, port, jsonPayload);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to send motion packet to {TargetIp}:{Port}", targetIp, port);
            throw;
        }
    }

    /// <summary>
    /// Sends a safety packet via TCP
    /// </summary>
    public async Task SendSafetyPacketAsync(string targetIp, int port, SafetyPacketEntity packet)
    {
        try
        {
            var jsonPayload = CreateSafetyPacketJson(packet);
            var data = Encoding.UTF8.GetBytes(jsonPayload);
            
            if (!_tcpClient.Connected)
            {
                await _tcpClient.ConnectAsync(targetIp, port);
            }
            
            var stream = _tcpClient.GetStream();
            await stream.WriteAsync(data);
            await stream.FlushAsync();
            
            _logger.LogInformation("Sent safety packet to {TargetIp}:{Port} - {Payload}", targetIp, port, jsonPayload);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to send safety packet to {TargetIp}:{Port}", targetIp, port);
            throw;
        }
    }

    /// <summary>
    /// Sends an OnVIF packet via HTTP
    /// </summary>
    public async Task SendOnVIFPacketAsync(string targetIp, int port, OnVIFPacketEntity packet)
    {
        try
        {
            var jsonPayload = CreateOnVIFPacketJson(packet);
            var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");
            
            var url = $"http://{targetIp}:{port}/onvif/event";
            var response = await _httpClient.PostAsync(url, content);
            
            _logger.LogInformation("Sent OnVIF packet to {Url} - {Payload}", url, jsonPayload);
            _logger.LogInformation("Response status: {StatusCode}", response.StatusCode);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to send OnVIF packet to {TargetIp}:{Port}", targetIp, port);
            throw;
        }
    }

    /// <summary>
    /// Blasts multiple packets of the same type
    /// </summary>
    public async Task BlastPacketsAsync<T>(string targetIp, int port, IEnumerable<T> packets, string protocol) where T : BasePacketEntity
    {
        var packetList = packets.ToList();
        _logger.LogInformation("Starting to blast {Count} {Type} packets to {TargetIp}:{Port} via {Protocol}", 
            packetList.Count, typeof(T).Name, targetIp, port, protocol);

        var tasks = new List<Task>();

        foreach (var packet in packetList)
        {
            Task task = packet switch
            {
                MotionPacketEntity motionPacket => SendMotionPacketAsync(targetIp, port, motionPacket),
                SafetyPacketEntity safetyPacket => SendSafetyPacketAsync(targetIp, port, safetyPacket),
                OnVIFPacketEntity onvifPacket => SendOnVIFPacketAsync(targetIp, port, onvifPacket),
                _ => throw new ArgumentException($"Unsupported packet type: {packet.GetType().Name}")
            };

            tasks.Add(task);
            
            // Small delay between packets to avoid overwhelming the network
            await Task.Delay(10);
        }

        await Task.WhenAll(tasks);
        _logger.LogInformation("Finished blasting {Count} packets", packetList.Count);
    }

    /// <summary>
    /// Creates a random motion packet for testing
    /// </summary>
    public static MotionPacketEntity CreateRandomMotionPacket()
    {
        var random = new Random();
        var opCodes = new[] { "MOTION_DETECTED", "MOTION_STOPPED", "MOTION_ALERT", "MOTION_WARNING" };
        var descriptions = new[] { "Motion sensor triggered", "Motion stopped", "Motion alert", "Motion warning" };

        return new MotionPacketEntity
        {
            Id = Guid.NewGuid(),
            Timestamp = DateTime.UtcNow,
            Type = random.Next(2) == 1,
            OpCode = opCodes[random.Next(opCodes.Length)],
            OpCodeDescription = descriptions[random.Next(descriptions.Length)],
            Axis = random.Next(1, 4),
            FloatValue = (float)(random.NextDouble() * 100)
        };
    }

    /// <summary>
    /// Creates a random safety packet for testing
    /// </summary>
    public static SafetyPacketEntity CreateRandomSafetyPacket()
    {
        var random = new Random();
        var opCodes = new[] { "SAFETY_ALERT", "EMERGENCY_STOP", "THRESHOLD_WARNING", "SAFETY_OK" };
        var descriptions = new[] { "Safety system alert", "Emergency stop activated", "Safety threshold warning", "Safety system OK" };

        return new SafetyPacketEntity
        {
            Id = Guid.NewGuid(),
            Timestamp = DateTime.UtcNow,
            Type = random.Next(2) == 1,
            OpCode = opCodes[random.Next(opCodes.Length)],
            OpCodeDescription = descriptions[random.Next(descriptions.Length)],
            Axis = random.Next(1, 4),
            FloatValue = (float)(random.NextDouble() * 100)
        };
    }

    /// <summary>
    /// Creates a random OnVIF packet for testing
    /// </summary>
    public static OnVIFPacketEntity CreateRandomOnVIFPacket()
    {
        var random = new Random();
        var opCodes = new[] { "CAMERA_MOTION", "CAMERA_OFFLINE", "STREAM_STARTED", "PTZ_MOVE" };
        var descriptions = new[] { "Camera detected motion", "Camera went offline", "Video stream started", "PTZ camera movement" };

        return new OnVIFPacketEntity
        {
            Id = Guid.NewGuid(),
            Timestamp = DateTime.UtcNow,
            Type = random.Next(2) == 1,
            OpCode = opCodes[random.Next(opCodes.Length)],
            OpCodeDescription = descriptions[random.Next(descriptions.Length)],
            Axis = random.Next(1, 4),
            FloatValue = (float)(random.NextDouble() * 100)
        };
    }

    /// <summary>
    /// Creates multiple random packets of the specified type
    /// </summary>
    public static IEnumerable<T> CreateRandomPackets<T>(int count) where T : BasePacketEntity
    {
        for (int i = 0; i < count; i++)
        {
            yield return typeof(T).Name switch
            {
                nameof(MotionPacketEntity) => (T)(BasePacketEntity)CreateRandomMotionPacket(),
                nameof(SafetyPacketEntity) => (T)(BasePacketEntity)CreateRandomSafetyPacket(),
                nameof(OnVIFPacketEntity) => (T)(BasePacketEntity)CreateRandomOnVIFPacket(),
                _ => throw new ArgumentException($"Unsupported packet type: {typeof(T).Name}")
            };
        }
    }

    private static string CreateMotionPacketJson(MotionPacketEntity packet)
    {
        return $$"""
        {
            "type": {{packet.Type.ToString().ToLower()}},
            "opcode": "{{packet.OpCode}}",
            "opcodedescription": "{{packet.OpCodeDescription}}",
            "axis": {{packet.Axis}},
            "floatvalue": {{packet.FloatValue}}
        }
        """;
    }

    private static string CreateSafetyPacketJson(SafetyPacketEntity packet)
    {
        return $$"""
        {
            "type": {{packet.Type.ToString().ToLower()}},
            "opcode": "{{packet.OpCode}}",
            "opcodedescription": "{{packet.OpCodeDescription}}",
            "axis": {{packet.Axis}},
            "floatvalue": {{packet.FloatValue}}
        }
        """;
    }

    private static string CreateOnVIFPacketJson(OnVIFPacketEntity packet)
    {
        return $$"""
        {
            "type": {{packet.Type.ToString().ToLower()}},
            "opcode": "{{packet.OpCode}}",
            "opcodedescription": "{{packet.OpCodeDescription}}",
            "axis": {{packet.Axis}},
            "floatvalue": {{packet.FloatValue}}
        }
        """;
    }

    public void Dispose()
    {
        if (!_disposed)
        {
            _udpClient?.Dispose();
            _tcpClient?.Dispose();
            _httpClient?.Dispose();
            _disposed = true;
        }
    }
}
