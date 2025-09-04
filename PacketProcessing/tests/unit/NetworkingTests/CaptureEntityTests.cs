using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PacketProcessing.Services.Networking;
using PacketProcessing.Entities.Packet;
using System.Threading.Channels;
using Xunit;

namespace PacketProcessing.Tests.Unit.NetworkingTests;

/// <summary>
/// Tests for capture services with mock packet server integration
/// </summary>
public class CaptureEntityTests : IDisposable
{
    private readonly ServiceProvider _serviceProvider;
    private readonly ILogger<MotionCaptureService> _motionLogger;
    private readonly ILogger<SafetyCaptureService> _safetyLogger;
    private readonly ILogger<OnVIFCaptureService> _onvifLogger;
    private readonly IConfiguration _configuration;
    private readonly Channel<MotionPacketEntity> _motionChannel;
    private readonly Channel<SafetyPacketEntity> _safetyChannel;
    private readonly Channel<OnVIFPacketEntity> _onvifChannel;

    public CaptureEntityTests()
    {
        // Setup services
        var services = new ServiceCollection();
        
        // Add logging
        services.AddLogging(builder => builder.AddConsole().SetMinimumLevel(LogLevel.Debug));
        
        // Add configuration
        var configBuilder = new ConfigurationBuilder();
        configBuilder.AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["DataPipes:MotionCapture:Sampling:IntervalMs"] = "100",
            ["DataPipes:SafetyCapture:Sampling:IntervalMs"] = "100",
            ["DataPipes:OnVIFCapture:Sampling:IntervalMs"] = "100",
            // Ensure correct protocol filters for captures
            ["DataPipes:MotionCapture:Network:Protocol"] = "tcp",
            ["DataPipes:SafetyCapture:Network:Protocol"] = "udp",
            ["DataPipes:OnVIFCapture:Network:Protocol"] = "http"
        });
        _configuration = configBuilder.Build();
        services.AddSingleton(_configuration);
        
        // Add channels
        _motionChannel = Channel.CreateBounded<MotionPacketEntity>(new BoundedChannelOptions(1000)
        {
            FullMode = BoundedChannelFullMode.Wait,
            SingleReader = false,
            SingleWriter = false
        });
        
        _safetyChannel = Channel.CreateBounded<SafetyPacketEntity>(new BoundedChannelOptions(1000)
        {
            FullMode = BoundedChannelFullMode.Wait,
            SingleReader = false,
            SingleWriter = false
        });
        
        _onvifChannel = Channel.CreateBounded<OnVIFPacketEntity>(new BoundedChannelOptions(1000)
        {
            FullMode = BoundedChannelFullMode.Wait,
            SingleReader = false,
            SingleWriter = false
        });
        
        services.AddSingleton(_motionChannel);
        services.AddSingleton(_safetyChannel);
        services.AddSingleton(_onvifChannel);
        
        _serviceProvider = services.BuildServiceProvider();
        
        _motionLogger = _serviceProvider.GetRequiredService<ILogger<MotionCaptureService>>();
        _safetyLogger = _serviceProvider.GetRequiredService<ILogger<SafetyCaptureService>>();
        _onvifLogger = _serviceProvider.GetRequiredService<ILogger<OnVIFCaptureService>>();
    }

    [Fact]
    public async Task MotionCaptureService_ShouldCaptureMotionPackets()
    {
        Console.WriteLine("📦 Testing Motion Capture Service with Mock Server");
        Console.WriteLine("=================================================");
        
        // Arrange
        var motionService = new MotionCaptureService(_motionLogger, _configuration, _motionChannel);
        var mockServer = new BinaryMockPacketServer("tcp", "motion", 3, 1); // 3 packets for 1 second
        
        var capturedPackets = new List<MotionPacketEntity>();
        var channelReader = _motionChannel.Reader;
        
        Console.WriteLine("✓ Motion capture service and mock server created");
        
        try
        {
            // Start the mock server
            await mockServer.StartServerAsync();
            var serverPort = mockServer.GetTcpPort();
            Console.WriteLine($"✓ Mock server started on port {serverPort}");
            
            // Start the capture service
            await motionService.StartCaptureAsync();
            Console.WriteLine("✓ Motion capture service started");
            
            // Start reading from channel in background
            var readCts = new CancellationTokenSource(TimeSpan.FromSeconds(6));
            var readTask = Task.Run(async () =>
            {
                try
                {
                    while (!readCts.IsCancellationRequested && capturedPackets.Count < 3)
                    {
                        if (await channelReader.WaitToReadAsync(readCts.Token))
                        {
                            while (channelReader.TryRead(out var packet))
                            {
                                capturedPackets.Add(packet);
                                Console.WriteLine($"✓ Captured motion packet: OpCode={packet.OpCode}, Axis={packet.Axis}, FloatValue={packet.FloatValue}");
                                if (capturedPackets.Count >= 3) break;
                            }
                        }
                    }
                }
                catch (OperationCanceledException) { }
            });
            
            // Wait for packets to be captured
            await Task.Delay(5000); // Wait 5 seconds to ensure we get the packets
            
            // Stop services
            await motionService.StopCaptureAsync();
            mockServer.Stop();
            
            // Wait for read task to complete
            await readTask;
            
            // Assert
            Assert.True(capturedPackets.Count >= 1, $"Expected at least 1 packet, but got {capturedPackets.Count}");
            
            foreach (var packet in capturedPackets)
            {
                Assert.NotNull(packet);
                Assert.NotNull(packet.OpCode);
                Assert.NotNull(packet.OpCodeDescription);
                Assert.True(packet.Axis >= 0 && packet.Axis <= 5);
            }
            
            Console.WriteLine($"✓ Successfully captured {capturedPackets.Count} motion packets");
            Console.WriteLine("✅ Motion Capture Service Test PASSED!\n");
        }
        finally
        {
            await motionService.StopCaptureAsync();
            motionService.Dispose();
            mockServer.Dispose();
        }
    }

    [Fact]
    public async Task SafetyCaptureService_ShouldCaptureSafetyPackets()
    {
        Console.WriteLine("📦 Testing Safety Capture Service with Mock Server");
        Console.WriteLine("=================================================");
        
        // Arrange
        var safetyService = new SafetyCaptureService(_safetyLogger, _configuration, _safetyChannel);
        var mockServer = new BinaryMockPacketServer("udp", "safety", 3, 1); // 3 packets for 1 second
        
        var capturedPackets = new List<SafetyPacketEntity>();
        var channelReader = _safetyChannel.Reader;
        
        Console.WriteLine("✓ Safety capture service and mock server created");
        
        try
        {
            // Start the mock server
            await mockServer.StartServerAsync();
            var serverPort = mockServer.GetUdpPort();
            Console.WriteLine($"✓ Mock server started on port {serverPort}");
            
            // Start the capture service
            await safetyService.StartCaptureAsync();
            Console.WriteLine("✓ Safety capture service started");
            
            // Start reading from channel in background
            var readCts = new CancellationTokenSource(TimeSpan.FromSeconds(6));
            var readTask = Task.Run(async () =>
            {
                try
                {
                    while (!readCts.IsCancellationRequested && capturedPackets.Count < 3)
                    {
                        if (await channelReader.WaitToReadAsync(readCts.Token))
                        {
                            while (channelReader.TryRead(out var packet))
                            {
                                capturedPackets.Add(packet);
                                Console.WriteLine($"✓ Captured safety packet: OpCode={packet.OpCode}, State={packet.State}");
                                if (capturedPackets.Count >= 3) break;
                            }
                        }
                    }
                }
                catch (OperationCanceledException) { }
            });
            
            // Wait for packets to be captured
            await Task.Delay(5000); // Wait 5 seconds to ensure we get the packets
            
            // Stop services
            await safetyService.StopCaptureAsync();
            mockServer.Stop();
            
            // Wait for read task to complete
            await readTask;
            
            // Assert
            Assert.True(capturedPackets.Count >= 1, $"Expected at least 1 packet, but got {capturedPackets.Count}");
            
            foreach (var packet in capturedPackets)
            {
                Assert.NotNull(packet);
                Assert.NotNull(packet.OpCode);
                Assert.NotNull(packet.OpCodeDescription);
                Assert.NotNull(packet.State);
            }
            
            Console.WriteLine($"✓ Successfully captured {capturedPackets.Count} safety packets");
            Console.WriteLine("✅ Safety Capture Service Test PASSED!\n");
        }
        finally
        {
            await safetyService.StopCaptureAsync();
            safetyService.Dispose();
            mockServer.Dispose();
        }
    }

    [Fact]
    public async Task OnVifCaptureService_ShouldCaptureOnVifPackets()
    {
        Console.WriteLine("📦 Testing OnVIF Capture Service with Mock Server");
        Console.WriteLine("================================================");
        
        // Arrange
        var onvifService = new OnVIFCaptureService(_onvifLogger, _configuration, _onvifChannel);
        var mockServer = new BinaryMockPacketServer("http", "onvif", 3, 3); // 3 packets for 3 seconds
        
        var capturedPackets = new List<OnVIFPacketEntity>();
        var channelReader = _onvifChannel.Reader;
        
        Console.WriteLine("✓ OnVIF capture service and mock server created");
        
        try
        {
            // Start the mock server
            await mockServer.StartServerAsync();
            Console.WriteLine("✓ Mock server started");
            
            // Start the capture service
            await onvifService.StartCaptureAsync();
            Console.WriteLine("✓ OnVIF capture service started");
            
            // Give capture service time to initialize
            await Task.Delay(1000);
            
            // Start reading from channel in background
            var readCts = new CancellationTokenSource(TimeSpan.FromSeconds(6));
            var readTask = Task.Run(async () =>
            {
                try
                {
                    while (!readCts.IsCancellationRequested && capturedPackets.Count < 3)
                    {
                        if (await channelReader.WaitToReadAsync(readCts.Token))
                        {
                            while (channelReader.TryRead(out var packet))
                            {
                                capturedPackets.Add(packet);
                                Console.WriteLine($"✓ Captured OnVIF packet: Description={packet.Description}, Measurement={packet.Measurement}");
                                if (capturedPackets.Count >= 3) break;
                            }
                        }
                    }
                }
                catch (OperationCanceledException) { }
            });
            
            // Wait for packets to be captured
            await Task.Delay(5000); // Wait 5 seconds to ensure we get the packets
            
            // Stop services
            await onvifService.StopCaptureAsync();
            mockServer.Stop();
            
            // Wait for read task to complete
            await readTask;
            
            // Assert
            Assert.True(capturedPackets.Count >= 1, $"Expected at least 1 OnVIF packet, but got {capturedPackets.Count}");
            Console.WriteLine($"✓ Successfully captured {capturedPackets.Count} OnVIF packets");
            
            foreach (var packet in capturedPackets)
            {
                Assert.NotNull(packet);
                Assert.NotNull(packet.Description);
                Assert.True(packet.Measurement >= 0);
            }
            
            Console.WriteLine("✅ OnVIF Capture Service Test PASSED!\n");
        }
        finally
        {
            await onvifService.StopCaptureAsync();
            onvifService.Dispose();
            mockServer.Dispose();
        }
    }

    public void Dispose()
    {
        _serviceProvider?.Dispose();
    }
}
