using System.Net;
using System.Net.Sockets;
using Xunit;

namespace PacketProcessing.Tests;

public class UdpPacketSenderTests
{
    [Fact]
    public async Task SendUdpPackets_ShouldSendSpecifiedNumberOfPackets()
    {
        // Arrange
        var host = "127.0.0.1";
        var port = 5000;
        var packetsPerSecond = 100;
        var payloadSize = 256;
        var durationSeconds = 5;
        var expectedPackets = packetsPerSecond * durationSeconds;

        // Act
        var sentPackets = await SendUdpPackets(host, port, packetsPerSecond, payloadSize, durationSeconds);

        // Assert
        Assert.True(sentPackets > 0, "Should have sent some packets");
        Assert.True(sentPackets >= expectedPackets * 0.8, $"Should have sent at least 80% of expected packets. Expected: {expectedPackets}, Actual: {sentPackets}");
    }

    [Fact]
    public async Task SendUdpPackets_WithHighRate_ShouldHandleHighThroughput()
    {
        // Arrange
        var host = "127.0.0.1";
        var port = 5000;
        var packetsPerSecond = 1000;
        var payloadSize = 512;
        var durationSeconds = 3;

        // Act
        var sentPackets = await SendUdpPackets(host, port, packetsPerSecond, payloadSize, durationSeconds);

        // Assert
        Assert.True(sentPackets > 0, "Should have sent some packets");
        Console.WriteLine($"Sent {sentPackets} packets at {packetsPerSecond} pps");
    }

    private async Task<int> SendUdpPackets(string host, int port, int packetsPerSecond, int payloadSize, int durationSeconds)
    {
        Console.WriteLine($"UDP Test - Blasting to {host}:{port} at ~{packetsPerSecond} pps, payload={payloadSize} bytes, duration={durationSeconds}s");

        using var client = new UdpClient();
        var endPoint = new IPEndPoint(IPAddress.Parse(host), port);

        var random = new Random();
        var payload = new byte[payloadSize];
        random.NextBytes(payload);

        var tickHz = 100; // 100 ticks/sec -> 10ms per tick
        var packetsPerTick = Math.Max(1, packetsPerSecond / tickHz);
        var tickInterval = 1000.0 / tickHz; // milliseconds

        var endTime = DateTime.UtcNow.AddSeconds(durationSeconds);
        var nextTick = DateTime.UtcNow;
        var sentTotal = 0;

        while (DateTime.UtcNow < endTime)
        {
            // Send a burst for this tick
            for (int i = 0; i < packetsPerTick; i++)
            {
                // Include a counter in first 8 bytes to help validation
                var counter = (ulong)sentTotal & 0xFFFFFFFFFFFFFFFF;
                var counterBytes = BitConverter.GetBytes(counter);
                
                // Create payload with counter
                var packetData = new byte[payloadSize];
                if (payloadSize >= 8)
                {
                    Array.Copy(counterBytes, 0, packetData, 0, 8);
                    Array.Copy(payload, 8, packetData, 8, payloadSize - 8);
                }
                else
                {
                    Array.Copy(payload, packetData, payloadSize);
                }

                client.Send(packetData, packetData.Length, endPoint);
                sentTotal++;
            }

            nextTick = nextTick.AddMilliseconds(tickInterval);
            
            // Sleep until next tick
            var now = DateTime.UtcNow;
            var sleepTime = nextTick - now;
            if (sleepTime.TotalMilliseconds > 2) // Coarse sleep for >=2ms
            {
                await Task.Delay((int)(sleepTime.TotalMilliseconds - 1));
            }
            
            // Spin if needed for precise timing
            while (DateTime.UtcNow < nextTick)
            {
                await Task.Delay(1);
            }
        }

        Console.WriteLine($"Done. Sent ~{sentTotal} packets.");
        return sentTotal;
    }
}
