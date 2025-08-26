using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Collections.Concurrent;
using System.Threading.Channels;
using PacketProcessing.Entities;
using PacketProcessing.Services.Networking;
using Moq;
using FluentAssertions;
using Xunit;

namespace PacketProcessing.Tests.CaptureServicesTests;

/// <summary>
/// Base test class for capture services with common setup and utilities
/// </summary>
public abstract class BaseCaptureServiceTests<T> where T : BasePacketEntity
{
    protected readonly Mock<ILogger<BaseCaptureService<T>>> _loggerMock;
    protected readonly Mock<IConfiguration> _configurationMock;
    protected readonly ConcurrentDictionary<string, LibPcap.LibPcapLiveDevice> _activeDevices;
    protected readonly Channel<T> _testChannel;
    protected readonly BaseCaptureService<T> _captureService;

    protected BaseCaptureServiceTests()
    {
        _loggerMock = new Mock<ILogger<BaseCaptureService<T>>>();
        _configurationMock = new Mock<IConfiguration>();
        _activeDevices = new ConcurrentDictionary<string, LibPcap.LibPcapLiveDevice>();
        
        // Create a test channel
        _testChannel = Channel.CreateBounded<T>(new BoundedChannelOptions(1000)
        {
            FullMode = BoundedChannelFullMode.Wait
        });
    }

    /// <summary>
    /// Creates a mock configuration section for testing
    /// </summary>
    protected IConfigurationSection CreateMockConfigurationSection(string dataPipeName, string protocol, string[] ips, int maxMembers)
    {
        var dataPipeSection = new Mock<IConfigurationSection>();
        var channelSection = new Mock<IConfigurationSection>();
        var networkSection = new Mock<IConfigurationSection>();
        var ipsSection = new Mock<IConfigurationSection>();

        // Setup channel section
        channelSection.Setup(x => x.GetValue<int>("Members")).Returns(maxMembers);
        dataPipeSection.Setup(x => x.GetSection("Channel")).Returns(channelSection.Object);

        // Setup network section
        networkSection.Setup(x => x.GetValue<string>("Protocol")).Returns(protocol);
        networkSection.Setup(x => x.GetSection("IPs")).Returns(ipsSection.Object);
        ipsSection.Setup(x => x.Get<string[]>()).Returns(ips);
        dataPipeSection.Setup(x => x.GetSection("Network")).Returns(networkSection.Object);

        return dataPipeSection.Object;
    }

    /// <summary>
    /// Creates a test packet payload as JSON bytes
    /// </summary>
    protected byte[] CreateTestPacketPayload(string jsonPayload)
    {
        return System.Text.Encoding.UTF8.GetBytes(jsonPayload);
    }

    /// <summary>
    /// Creates a mock LibPcap device for testing
    /// </summary>
    protected Mock<LibPcap.LibPcapLiveDevice> CreateMockDevice(string deviceName)
    {
        var deviceMock = new Mock<LibPcap.LibPcapLiveDevice>();
        deviceMock.Setup(x => x.Name).Returns(deviceName);
        deviceMock.Setup(x => x.Started).Returns(false);
        return deviceMock;
    }

    /// <summary>
    /// Waits for a packet to be written to the channel with timeout
    /// </summary>
    protected async Task<T?> WaitForPacketAsync(TimeSpan timeout = default)
    {
        if (timeout == default)
            timeout = TimeSpan.FromSeconds(5);

        using var cts = new CancellationTokenSource(timeout);
        
        try
        {
            return await _testChannel.Reader.ReadAsync(cts.Token);
        }
        catch (OperationCanceledException)
        {
            return null; // Timeout
        }
    }

    /// <summary>
    /// Asserts that a packet was written to the channel
    /// </summary>
    protected async Task<T> AssertPacketWrittenAsync(string expectedErrorMessage = "Expected packet to be written to channel")
    {
        var packet = await WaitForPacketAsync();
        packet.Should().NotBeNull(expectedErrorMessage);
        return packet!;
    }

    /// <summary>
    /// Asserts that no packet was written to the channel
    /// </summary>
    protected async Task AssertNoPacketWrittenAsync(string expectedErrorMessage = "Expected no packet to be written to channel")
    {
        var packet = await WaitForPacketAsync(TimeSpan.FromMilliseconds(100));
        packet.Should().BeNull(expectedErrorMessage);
    }

    /// <summary>
    /// Creates a test capture service instance
    /// </summary>
    protected abstract BaseCaptureService<T> CreateCaptureService(string dataPipeName);

    /// <summary>
    /// Gets the expected filter for the service
    /// </summary>
    protected abstract string GetExpectedFilter(string protocol, string[] ips);

    /// <summary>
    /// Creates a valid test packet payload for the specific service
    /// </summary>
    protected abstract string CreateValidTestPayload();

    /// <summary>
    /// Creates an invalid test packet payload for the specific service
    /// </summary>
    protected abstract string CreateInvalidTestPayload();
}
