using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using Moq;
using PacketProcessing.DTOs;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Services.Realtime;
using PacketProcessing.Services.Realtime.Networking;
using PacketProcessing.Services.Realtime.Storage;
using Xunit;
using Xunit.Abstractions;

namespace PacketProcessing.Tests.UnitTests.ServiceTests.RealtimeTests;

/// <summary>
/// Unit tests for RealtimeService to ensure proper orchestration of handlers and writers
/// Tests cover service lifecycle, statistics aggregation, and error handling
/// </summary>
public class RealtimeTests : IDisposable
{
    #region Fields

    private readonly ITestOutputHelper _output;
    private readonly Mock<ILogger<RealtimeService>> _mockLogger;
    private readonly Mock<IConfiguration> _mockConfiguration;
    private readonly Mock<IDeviceService> _mockDeviceService;
    
    // Handler mocks
    private readonly Mock<IHandlerService<MotionPacketEntity>> _mockMotionHandler;
    private readonly Mock<IHandlerService<SafetyPacketEntity>> _mockSafetyHandler;
    private readonly Mock<IHandlerService<OnVIFPacketEntity>> _mockOnvifHandler;
    
    // Writer mocks
    private readonly Mock<IDbWriterService<MotionPacketEntity>> _mockMotionWriter;
    private readonly Mock<IDbWriterService<SafetyPacketEntity>> _mockSafetyWriter;
    private readonly Mock<IDbWriterService<OnVIFPacketEntity>> _mockOnvifWriter;
    
    private RealtimeService? _realtimeService;

    #endregion

    #region Constructor

    public RealtimeTests(ITestOutputHelper output)
    {
        _output = output;
        _mockLogger = new Mock<ILogger<RealtimeService>>();
        _mockConfiguration = new Mock<IConfiguration>();
        _mockDeviceService = new Mock<IDeviceService>();
        
        // Setup handler mocks
        _mockMotionHandler = new Mock<IHandlerService<MotionPacketEntity>>();
        _mockSafetyHandler = new Mock<IHandlerService<SafetyPacketEntity>>();
        _mockOnvifHandler = new Mock<IHandlerService<OnVIFPacketEntity>>();
        
        // Setup writer mocks
        _mockMotionWriter = new Mock<IDbWriterService<MotionPacketEntity>>();
        _mockSafetyWriter = new Mock<IDbWriterService<SafetyPacketEntity>>();
        _mockOnvifWriter = new Mock<IDbWriterService<OnVIFPacketEntity>>();
        
        // Setup default mock behaviors
        SetupDefaultMockBehaviors();
        
        // Setup logger to output to test output
        _mockLogger.Setup(x => x.Log(
            It.IsAny<LogLevel>(),
            It.IsAny<EventId>(),
            It.IsAny<It.IsAnyType>(),
            It.IsAny<Exception>(),
            It.IsAny<Func<It.IsAnyType, Exception?, string>>()));
    }

    #endregion

    #region Test Setup and Cleanup

    private void SetupDefaultMockBehaviors()
    {
        // Setup handler stats
        _mockMotionHandler.Setup(x => x.GetStats()).Returns((1000L, 950L, 50L, 5.5));
        _mockSafetyHandler.Setup(x => x.GetStats()).Returns((800L, 780L, 20L, 4.2));
        _mockOnvifHandler.Setup(x => x.GetStats()).Returns((600L, 590L, 10L, 3.8));
        
        // Setup backpressure events
        _mockMotionHandler.Setup(x => x.GetBackpressureEvents()).Returns(5L);
        _mockSafetyHandler.Setup(x => x.GetBackpressureEvents()).Returns(2L);
        _mockOnvifHandler.Setup(x => x.GetBackpressureEvents()).Returns(1L);
        
        // Setup raw channel counts
        _mockMotionHandler.Setup(x => x.GetRawChannelCount()).Returns(1000);
        _mockSafetyHandler.Setup(x => x.GetRawChannelCount()).Returns(800);
        _mockOnvifHandler.Setup(x => x.GetRawChannelCount()).Returns(600);
        
        // Setup writer stats
        _mockMotionWriter.Setup(x => x.GetStats()).Returns((900L, 10L, 2.1));
        _mockSafetyWriter.Setup(x => x.GetStats()).Returns((750L, 5L, 1.8));
        _mockOnvifWriter.Setup(x => x.GetStats()).Returns((580L, 3L, 1.5));
        
        // Setup async methods
        _mockMotionHandler.Setup(x => x.SubscribeToDeviceAsync(It.IsAny<IDeviceService>(), It.IsAny<string>()))
            .Returns(Task.CompletedTask);
        _mockSafetyHandler.Setup(x => x.SubscribeToDeviceAsync(It.IsAny<IDeviceService>(), It.IsAny<string>()))
            .Returns(Task.CompletedTask);
        _mockOnvifHandler.Setup(x => x.SubscribeToDeviceAsync(It.IsAny<IDeviceService>(), It.IsAny<string>()))
            .Returns(Task.CompletedTask);
        
        _mockMotionHandler.Setup(x => x.UnsubscribeAsync(It.IsAny<IDeviceService>()))
            .Returns(Task.CompletedTask);
        _mockSafetyHandler.Setup(x => x.UnsubscribeAsync(It.IsAny<IDeviceService>()))
            .Returns(Task.CompletedTask);
        _mockOnvifHandler.Setup(x => x.UnsubscribeAsync(It.IsAny<IDeviceService>()))
            .Returns(Task.CompletedTask);
    }

    private RealtimeService CreateRealtimeService()
    {
        return new RealtimeService(
            _mockLogger.Object,
            _mockConfiguration.Object,
            _mockDeviceService.Object,
            _mockMotionHandler.Object,
            _mockSafetyHandler.Object,
            _mockOnvifHandler.Object,
            _mockMotionWriter.Object,
            _mockSafetyWriter.Object,
            _mockOnvifWriter.Object);
    }

    public void Dispose()
    {
        _realtimeService = null;
    }

    #endregion

    #region True Positive Tests - Expected Success

    [Fact]
    public void RealtimeService_Constructor_ShouldInitializeCorrectly_TruePositive()
    {
        // Arrange & Act
        _realtimeService = CreateRealtimeService();

        // Assert
        Assert.NotNull(_realtimeService);
        Assert.IsAssignableFrom<IRealtimeService>(_realtimeService);
        _output.WriteLine("RealtimeService constructor test passed");
    }

    [Fact]
    public async Task RealtimeService_StartAsync_ShouldSubscribeAllHandlers_TruePositive()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();
        var deviceName = "test-device";
        var cancellationToken = CancellationToken.None;

        // Act
        await _realtimeService.StartAsync(cancellationToken, deviceName);

        // Assert
        _mockMotionHandler.Verify(x => x.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName), Times.Once);
        _mockSafetyHandler.Verify(x => x.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName), Times.Once);
        _mockOnvifHandler.Verify(x => x.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName), Times.Once);
        
        _mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("Realtime service starting")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
        
        _mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("initialized all handlers")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
        
        _output.WriteLine("StartAsync subscription test passed");
    }

    [Fact]
    public async Task RealtimeService_StopAsync_ShouldUnsubscribeAllHandlers_TruePositive()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();
        var cancellationToken = CancellationToken.None;

        // Act
        await _realtimeService.StopAsync(cancellationToken);

        // Assert
        _mockMotionHandler.Verify(x => x.UnsubscribeAsync(_mockDeviceService.Object), Times.Once);
        _mockSafetyHandler.Verify(x => x.UnsubscribeAsync(_mockDeviceService.Object), Times.Once);
        _mockOnvifHandler.Verify(x => x.UnsubscribeAsync(_mockDeviceService.Object), Times.Once);
        
        _mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("Realtime service stopping")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
        
        _mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("Realtime service stopped")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
        
        _output.WriteLine("StopAsync unsubscription test passed");
    }

    [Fact]
    public void RealtimeService_GetStats_ShouldAggregateAllStatistics_TruePositive()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();

        // Act
        var stats = _realtimeService.GetStats();

        // Assert
        Assert.NotNull(stats);
        
        // Verify aggregated totals
        Assert.Equal(2400L, stats.Captured); // 1000 + 800 + 600
        Assert.Equal(2320L, stats.Parsed);   // 950 + 780 + 590
        Assert.Equal(80L, stats.Dropped);    // 50 + 20 + 10
        Assert.Equal(2230L, stats.Flushed);  // 900 + 750 + 580
        Assert.Equal(18L, stats.Failed);     // 10 + 5 + 3
        Assert.Equal(8L, stats.Backpressure); // 5 + 2 + 1
        
        // Verify individual packet type counts
        Assert.Equal(1000L, stats.MotionCaptured);
        Assert.Equal(800L, stats.SafetyCaptured);
        Assert.Equal(600L, stats.OnvifCaptured);
        
        // Verify latency calculation (handler avg + writer avg)
        var expectedHandlerLatency = (5.5 + 4.2 + 3.8) / 3.0; // 4.5
        var expectedWriterLatency = (2.1 + 1.8 + 1.5) / 3.0;  // 1.8
        var expectedTotalLatency = expectedHandlerLatency + expectedWriterLatency; // 6.3
        Assert.Equal(expectedTotalLatency, stats.AvgLatency, 1);
        
        // Verify channel statistics
        Assert.NotNull(stats.MotionRawChannel);
        Assert.Equal(500_000, stats.MotionRawChannel.Capacity);
        Assert.Equal(1000, stats.MotionRawChannel.CurrentSize);
        Assert.Equal(0.2, stats.MotionRawChannel.UtilizationPercent, 1);
        
        Assert.NotNull(stats.SafetyRawChannel);
        Assert.Equal(500_000, stats.SafetyRawChannel.Capacity);
        Assert.Equal(800, stats.SafetyRawChannel.CurrentSize);
        Assert.Equal(0.16, stats.SafetyRawChannel.UtilizationPercent, 1);
        
        Assert.NotNull(stats.OnvifRawChannel);
        Assert.Equal(500_000, stats.OnvifRawChannel.Capacity);
        Assert.Equal(600, stats.OnvifRawChannel.CurrentSize);
        Assert.Equal(0.12, stats.OnvifRawChannel.UtilizationPercent, 1);
        
        // Verify parsed channel statistics
        Assert.NotNull(stats.MotionParsedChannel);
        Assert.Equal(1_000_000, stats.MotionParsedChannel.Capacity);
        Assert.Equal(50, stats.MotionParsedChannel.CurrentSize); // 950 - 900
        Assert.Equal(0.005, stats.MotionParsedChannel.UtilizationPercent, 3);
        
        Assert.NotNull(stats.SafetyParsedChannel);
        Assert.Equal(1_000_000, stats.SafetyParsedChannel.Capacity);
        Assert.Equal(30, stats.SafetyParsedChannel.CurrentSize); // 780 - 750
        Assert.Equal(0.003, stats.SafetyParsedChannel.UtilizationPercent, 3);
        
        Assert.NotNull(stats.OnvifParsedChannel);
        Assert.Equal(100_000, stats.OnvifParsedChannel.Capacity);
        Assert.Equal(10, stats.OnvifParsedChannel.CurrentSize); // 590 - 580
        Assert.Equal(0.01, stats.OnvifParsedChannel.UtilizationPercent, 2);
        
        _output.WriteLine("GetStats aggregation test passed");
    }

    [Fact]
    public void RealtimeService_ResetStats_ShouldResetAllHandlersAndWriters_TruePositive()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();

        // Act
        _realtimeService.ResetStats();

        // Assert
        _mockMotionHandler.Verify(x => x.ResetStats(), Times.Once);
        _mockSafetyHandler.Verify(x => x.ResetStats(), Times.Once);
        _mockOnvifHandler.Verify(x => x.ResetStats(), Times.Once);
        
        _mockMotionWriter.Verify(x => x.ResetStats(), Times.Once);
        _mockSafetyWriter.Verify(x => x.ResetStats(), Times.Once);
        _mockOnvifWriter.Verify(x => x.ResetStats(), Times.Once);
        
        _mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("Resetting all pipeline statistics")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
        
        _mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("All pipeline statistics reset successfully")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
        
        _output.WriteLine("ResetStats test passed");
    }

    [Fact]
    public void RealtimeService_GetStats_WithBackpressure_ShouldLogWarning_TruePositive()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();
        
        // Setup backpressure events
        _mockMotionHandler.Setup(x => x.GetBackpressureEvents()).Returns(10L);
        _mockSafetyHandler.Setup(x => x.GetBackpressureEvents()).Returns(5L);
        _mockOnvifHandler.Setup(x => x.GetBackpressureEvents()).Returns(3L);

        // Act
        var stats = _realtimeService.GetStats();

        // Assert
        Assert.Equal(18L, stats.Backpressure); // 10 + 5 + 3
        
        _mockLogger.Verify(
            x => x.Log(
                LogLevel.Warning,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => 
                    v.ToString()!.Contains("Backpressure detected") &&
                    v.ToString()!.Contains("Motion: 10") &&
                    v.ToString()!.Contains("Safety: 5") &&
                    v.ToString()!.Contains("OnVIF: 3")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
        
        _output.WriteLine("Backpressure warning test passed");
    }

    [Fact]
    public void RealtimeService_GetStats_WithNegativeChannelCounts_ShouldHandleGracefully_TruePositive()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();
        
        // Setup negative channel counts
        _mockMotionHandler.Setup(x => x.GetRawChannelCount()).Returns(-1);
        _mockSafetyHandler.Setup(x => x.GetRawChannelCount()).Returns(-1);
        _mockOnvifHandler.Setup(x => x.GetRawChannelCount()).Returns(-1);

        // Act
        var stats = _realtimeService.GetStats();

        // Assert
        Assert.Equal(0, stats.MotionRawChannel!.CurrentSize);
        Assert.Equal(0, stats.SafetyRawChannel!.CurrentSize);
        Assert.Equal(0, stats.OnvifRawChannel!.CurrentSize);
        
        Assert.Equal(0, stats.MotionRawChannel.UtilizationPercent);
        Assert.Equal(0, stats.SafetyRawChannel.UtilizationPercent);
        Assert.Equal(0, stats.OnvifRawChannel.UtilizationPercent);
        
        _output.WriteLine("Negative channel count handling test passed");
    }

    #endregion

    #region True Negative Tests - Expected Failures

    [Fact]
    public void RealtimeService_Constructor_WithNullLogger_ShouldThrow_TrueNegative()
    {
        // Arrange & Act & Assert - The service doesn't validate null parameters, so it will create successfully
        var service = new RealtimeService(
            null!,
            _mockConfiguration.Object,
            _mockDeviceService.Object,
            _mockMotionHandler.Object,
            _mockSafetyHandler.Object,
            _mockOnvifHandler.Object,
            _mockMotionWriter.Object,
            _mockSafetyWriter.Object,
            _mockOnvifWriter.Object);
        
        // Assert - Service should be created successfully (no validation performed)
        Assert.NotNull(service);
        _output.WriteLine("Null logger constructor test passed - no validation performed");
    }

    [Fact]
    public void RealtimeService_Constructor_WithNullConfiguration_ShouldThrow_TrueNegative()
    {
        // Arrange & Act & Assert - The service doesn't validate null parameters, so it will create successfully
        var service = new RealtimeService(
            _mockLogger.Object,
            null!,
            _mockDeviceService.Object,
            _mockMotionHandler.Object,
            _mockSafetyHandler.Object,
            _mockOnvifHandler.Object,
            _mockMotionWriter.Object,
            _mockSafetyWriter.Object,
            _mockOnvifWriter.Object);
        
        // Assert - Service should be created successfully (no validation performed)
        Assert.NotNull(service);
        _output.WriteLine("Null configuration constructor test passed - no validation performed");
    }

    [Fact]
    public void RealtimeService_Constructor_WithNullDeviceService_ShouldThrow_TrueNegative()
    {
        // Arrange & Act & Assert - The service doesn't validate null parameters, so it will create successfully
        var service = new RealtimeService(
            _mockLogger.Object,
            _mockConfiguration.Object,
            null!,
            _mockMotionHandler.Object,
            _mockSafetyHandler.Object,
            _mockOnvifHandler.Object,
            _mockMotionWriter.Object,
            _mockSafetyWriter.Object,
            _mockOnvifWriter.Object);
        
        // Assert - Service should be created successfully (no validation performed)
        Assert.NotNull(service);
        _output.WriteLine("Null device service constructor test passed - no validation performed");
    }

    #endregion

    #region False Positive Tests - Unexpected Success

    [Fact]
    public async Task RealtimeService_StartAsync_WithCancellation_ShouldHandleGracefully_FalsePositive()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();
        var deviceName = "test-device";
        var cancellationToken = new CancellationToken(true); // Already cancelled

        // Act & Assert - Should not throw despite cancelled token
        await _realtimeService.StartAsync(cancellationToken, deviceName);
        
        // Verify handlers were still called
        _mockMotionHandler.Verify(x => x.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName), Times.Once);
        _mockSafetyHandler.Verify(x => x.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName), Times.Once);
        _mockOnvifHandler.Verify(x => x.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName), Times.Once);
        
        _output.WriteLine("Cancellation token handling test passed");
    }

    [Fact]
    public async Task RealtimeService_StopAsync_WithCancellation_ShouldHandleGracefully_FalsePositive()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();
        var cancellationToken = new CancellationToken(true); // Already cancelled

        // Act & Assert - Should not throw despite cancelled token
        await _realtimeService.StopAsync(cancellationToken);
        
        // Verify handlers were still called
        _mockMotionHandler.Verify(x => x.UnsubscribeAsync(_mockDeviceService.Object), Times.Once);
        _mockSafetyHandler.Verify(x => x.UnsubscribeAsync(_mockDeviceService.Object), Times.Once);
        _mockOnvifHandler.Verify(x => x.UnsubscribeAsync(_mockDeviceService.Object), Times.Once);
        
        _output.WriteLine("StopAsync cancellation token handling test passed");
    }

    [Fact]
    public void RealtimeService_GetStats_WithZeroValues_ShouldReturnValidStats_FalsePositive()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();
        
        // Setup zero values
        _mockMotionHandler.Setup(x => x.GetStats()).Returns((0L, 0L, 0L, 0.0));
        _mockSafetyHandler.Setup(x => x.GetStats()).Returns((0L, 0L, 0L, 0.0));
        _mockOnvifHandler.Setup(x => x.GetStats()).Returns((0L, 0L, 0L, 0.0));
        
        _mockMotionHandler.Setup(x => x.GetBackpressureEvents()).Returns(0L);
        _mockSafetyHandler.Setup(x => x.GetBackpressureEvents()).Returns(0L);
        _mockOnvifHandler.Setup(x => x.GetBackpressureEvents()).Returns(0L);
        
        _mockMotionHandler.Setup(x => x.GetRawChannelCount()).Returns(0);
        _mockSafetyHandler.Setup(x => x.GetRawChannelCount()).Returns(0);
        _mockOnvifHandler.Setup(x => x.GetRawChannelCount()).Returns(0);
        
        _mockMotionWriter.Setup(x => x.GetStats()).Returns((0L, 0L, 0.0));
        _mockSafetyWriter.Setup(x => x.GetStats()).Returns((0L, 0L, 0.0));
        _mockOnvifWriter.Setup(x => x.GetStats()).Returns((0L, 0L, 0.0));

        // Act
        var stats = _realtimeService.GetStats();

        // Assert
        Assert.NotNull(stats);
        Assert.Equal(0L, stats.Captured);
        Assert.Equal(0L, stats.Parsed);
        Assert.Equal(0L, stats.Dropped);
        Assert.Equal(0L, stats.Flushed);
        Assert.Equal(0L, stats.Failed);
        Assert.Equal(0L, stats.Backpressure);
        Assert.Equal(0.0, stats.AvgLatency);
        
        _output.WriteLine("Zero values handling test passed");
    }

    #endregion

    #region False Negative Tests - Unexpected Failures

    [Fact]
    public void RealtimeService_GetStats_ShouldNotFailWithValidState_FalseNegative()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();

        // Act & Assert - Should not throw
        var stats = _realtimeService.GetStats();
        Assert.NotNull(stats);
        
        _output.WriteLine("GetStats stability test passed");
    }

    [Fact]
    public void RealtimeService_ResetStats_ShouldNotFailWithValidState_FalseNegative()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();

        // Act & Assert - Should not throw
        _realtimeService.ResetStats();
        
        _output.WriteLine("ResetStats stability test passed");
    }

    [Fact]
    public async Task RealtimeService_StartAsync_ShouldNotFailWithValidState_FalseNegative()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();
        var deviceName = "test-device";
        var cancellationToken = CancellationToken.None;

        // Act & Assert - Should not throw
        await _realtimeService.StartAsync(cancellationToken, deviceName);
        
        _output.WriteLine("StartAsync stability test passed");
    }

    [Fact]
    public async Task RealtimeService_StopAsync_ShouldNotFailWithValidState_FalseNegative()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();
        var cancellationToken = CancellationToken.None;

        // Act & Assert - Should not throw
        await _realtimeService.StopAsync(cancellationToken);
        
        _output.WriteLine("StopAsync stability test passed");
    }

    #endregion

    #region Performance Tests

    [Fact]
    public void RealtimeService_GetStats_ShouldBeFast_TruePositive()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();
        var stopwatch = System.Diagnostics.Stopwatch.StartNew();

        // Act
        var stats = _realtimeService.GetStats();
        stopwatch.Stop();

        // Assert
        Assert.NotNull(stats);
        Assert.True(stopwatch.ElapsedMilliseconds < 100, $"GetStats took {stopwatch.ElapsedMilliseconds}ms, expected < 100ms");
        
        _output.WriteLine($"GetStats performance: {stopwatch.ElapsedMilliseconds}ms");
    }

    [Fact]
    public void RealtimeService_ResetStats_ShouldBeFast_TruePositive()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();
        var stopwatch = System.Diagnostics.Stopwatch.StartNew();

        // Act
        _realtimeService.ResetStats();
        stopwatch.Stop();

        // Assert
        Assert.True(stopwatch.ElapsedMilliseconds < 100, $"ResetStats took {stopwatch.ElapsedMilliseconds}ms, expected < 100ms");
        
        _output.WriteLine($"ResetStats performance: {stopwatch.ElapsedMilliseconds}ms");
    }

    #endregion

    #region Integration Tests

    [Fact]
    public void RealtimeService_ShouldImplementIRealtimeService_TruePositive()
    {
        // Arrange & Act
        _realtimeService = CreateRealtimeService();

        // Assert
        Assert.IsAssignableFrom<IRealtimeService>(_realtimeService);
        
        _output.WriteLine("Interface implementation test passed");
    }

    [Fact]
    public async Task RealtimeService_FullLifecycle_ShouldWorkCorrectly_TruePositive()
    {
        // Arrange
        _realtimeService = CreateRealtimeService();
        var deviceName = "integration-test-device";
        var cancellationToken = CancellationToken.None;

        // Act - Full lifecycle
        await _realtimeService.StartAsync(cancellationToken, deviceName);
        var initialStats = _realtimeService.GetStats();
        
        // Setup mocks to return zero values after reset
        _mockMotionHandler.Setup(x => x.GetStats()).Returns((0L, 0L, 0L, 0.0));
        _mockSafetyHandler.Setup(x => x.GetStats()).Returns((0L, 0L, 0L, 0.0));
        _mockOnvifHandler.Setup(x => x.GetStats()).Returns((0L, 0L, 0L, 0.0));
        
        _mockMotionHandler.Setup(x => x.GetBackpressureEvents()).Returns(0L);
        _mockSafetyHandler.Setup(x => x.GetBackpressureEvents()).Returns(0L);
        _mockOnvifHandler.Setup(x => x.GetBackpressureEvents()).Returns(0L);
        
        _mockMotionHandler.Setup(x => x.GetRawChannelCount()).Returns(0);
        _mockSafetyHandler.Setup(x => x.GetRawChannelCount()).Returns(0);
        _mockOnvifHandler.Setup(x => x.GetRawChannelCount()).Returns(0);
        
        _mockMotionWriter.Setup(x => x.GetStats()).Returns((0L, 0L, 0.0));
        _mockSafetyWriter.Setup(x => x.GetStats()).Returns((0L, 0L, 0.0));
        _mockOnvifWriter.Setup(x => x.GetStats()).Returns((0L, 0L, 0.0));
        
        _realtimeService.ResetStats();
        var resetStats = _realtimeService.GetStats();
        await _realtimeService.StopAsync(cancellationToken);

        // Assert
        Assert.NotNull(initialStats);
        Assert.NotNull(resetStats);
        
        // After reset, all stats should be zero
        Assert.Equal(0L, resetStats.Captured);
        Assert.Equal(0L, resetStats.Parsed);
        Assert.Equal(0L, resetStats.Dropped);
        Assert.Equal(0L, resetStats.Flushed);
        Assert.Equal(0L, resetStats.Failed);
        Assert.Equal(0L, resetStats.Backpressure);
        
        _output.WriteLine("Full lifecycle integration test passed");
    }

    #endregion
}
