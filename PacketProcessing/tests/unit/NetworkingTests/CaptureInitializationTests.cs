using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PacketProcessing.Services.Networking;
using PacketProcessing.Entities.Packet;
using System.Threading.Channels;
using Xunit;

namespace PacketProcessing.Tests.Unit.NetworkingTests;

/// <summary>
/// Tests for capture service initialization and startup
/// </summary>
public class CaptureInitializationTests : IDisposable
{
    private readonly ServiceProvider _serviceProvider;
    private readonly ILogger<MotionCaptureService> _motionLogger;
    private readonly ILogger<SafetyCaptureService> _safetyLogger;
    private readonly ILogger<OnVIFCaptureService> _onvifLogger;
    private readonly IConfiguration _configuration;
    private readonly Channel<MotionPacketEntity> _motionChannel;
    private readonly Channel<SafetyPacketEntity> _safetyChannel;
    private readonly Channel<OnVIFPacketEntity> _onvifChannel;

    public CaptureInitializationTests()
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
            ["DataPipes:OnVIFCapture:Sampling:IntervalMs"] = "100"
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
    public void MotionCaptureService_ShouldInitializeNotRunning()
    {
        Console.WriteLine("🚀 Testing Motion Capture Service Initialization");
        Console.WriteLine("================================================");
        
        // Arrange & Act
        var motionService = new MotionCaptureService(_motionLogger, _configuration, _motionChannel);
        
        Console.WriteLine("✓ Motion capture service created");
        
        // Assert
        Assert.NotNull(motionService);
        Assert.False(motionService.IsCapturing);
        
        Console.WriteLine("✓ Service initialized successfully");
        Console.WriteLine("✓ Service is not running (as expected)");
        Console.WriteLine("✅ Motion Capture Service Initialization Test PASSED!\n");
        
        motionService.Dispose();
    }

    [Fact]
    public void SafetyCaptureService_ShouldInitializeNotRunning()
    {
        Console.WriteLine("🚀 Testing Safety Capture Service Initialization");
        Console.WriteLine("================================================");
        
        // Arrange & Act
        var safetyService = new SafetyCaptureService(_safetyLogger, _configuration, _safetyChannel);
        
        Console.WriteLine("✓ Safety capture service created");
        
        // Assert
        Assert.NotNull(safetyService);
        Assert.False(safetyService.IsCapturing);
        
        Console.WriteLine("✓ Service initialized successfully");
        Console.WriteLine("✓ Service is not running (as expected)");
        Console.WriteLine("✅ Safety Capture Service Initialization Test PASSED!\n");
        
        safetyService.Dispose();
    }

    [Fact]
    public void OnVifCaptureService_ShouldInitializeNotRunning()
    {
        Console.WriteLine("🚀 Testing OnVIF Capture Service Initialization");
        Console.WriteLine("================================================");
        
        // Arrange & Act
        var onvifService = new OnVIFCaptureService(_onvifLogger, _configuration, _onvifChannel);
        
        Console.WriteLine("✓ OnVIF capture service created");
        
        // Assert
        Assert.NotNull(onvifService);
        Assert.False(onvifService.IsCapturing);
        
        Console.WriteLine("✓ Service initialized successfully");
        Console.WriteLine("✓ Service is not running (as expected)");
        Console.WriteLine("✅ OnVIF Capture Service Initialization Test PASSED!\n");
        
        onvifService.Dispose();
    }

    [Fact]
    public async Task AllCaptureServices_ShouldStartAndBeReady()
    {
        Console.WriteLine("🚀 Testing All Capture Services Startup");
        Console.WriteLine("=======================================");
        
        // Arrange
        var motionService = new MotionCaptureService(_motionLogger, _configuration, _motionChannel);
        var safetyService = new SafetyCaptureService(_safetyLogger, _configuration, _safetyChannel);
        var onvifService = new OnVIFCaptureService(_onvifLogger, _configuration, _onvifChannel);
        
        Console.WriteLine("✓ All capture services created");
        
        try
        {
            // Act - Start all services
            await motionService.StartCaptureAsync();
            await safetyService.StartCaptureAsync();
            await onvifService.StartCaptureAsync();
            
            Console.WriteLine("✓ All services started");
            
            // Wait a moment for services to initialize
            await Task.Delay(1000);
            
            // Assert
            Assert.True(motionService.IsCapturing);
            Assert.True(safetyService.IsCapturing);
            Assert.True(onvifService.IsCapturing);
            
            Console.WriteLine("✓ All services are running and ready for capture");
            Console.WriteLine("✅ All Capture Services Startup Test PASSED!\n");
        }
        finally
        {
            // Cleanup
            await motionService.StopCaptureAsync();
            await safetyService.StopCaptureAsync();
            await onvifService.StopCaptureAsync();
            
            motionService.Dispose();
            safetyService.Dispose();
            onvifService.Dispose();
        }
    }

    [Fact]
    public async Task CaptureServices_ShouldHandleStartStopCycle()
    {
        Console.WriteLine("🔄 Testing Capture Services Start/Stop Cycle");
        Console.WriteLine("===========================================");
        
        // Arrange
        var motionService = new MotionCaptureService(_motionLogger, _configuration, _motionChannel);
        
        Console.WriteLine("✓ Motion capture service created");
        
        try
        {
            // Act & Assert - Start
            Assert.False(motionService.IsCapturing);
            await motionService.StartCaptureAsync();
            Assert.True(motionService.IsCapturing);
            Console.WriteLine("✓ Service started successfully");
            
            // Wait a moment
            await Task.Delay(500);
            
            // Act & Assert - Stop
            await motionService.StopCaptureAsync();
            Assert.False(motionService.IsCapturing);
            Console.WriteLine("✓ Service stopped successfully");
            
            // Act & Assert - Start again
            await motionService.StartCaptureAsync();
            Assert.True(motionService.IsCapturing);
            Console.WriteLine("✓ Service restarted successfully");
            
            Console.WriteLine("✅ Capture Services Start/Stop Cycle Test PASSED!\n");
        }
        finally
        {
            await motionService.StopCaptureAsync();
            motionService.Dispose();
        }
    }

    public void Dispose()
    {
        _serviceProvider?.Dispose();
    }
}
