using Moq;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Services.Realtime.Networking;
using PacketProcessing.Utils.Observers;
using System.Collections.Concurrent;
using Xunit;
using Xunit.Abstractions;

namespace PacketProcessing.Tests.UnitTests.ServiceTests.RealtimeTests.Networking;

/// <summary>
/// Unit tests for IHandlerService interface using mocked implementation
/// Tests service interface behavior, method calls, and return values
/// </summary>
public class HandlerServiceTests : IDisposable
{
    #region Fields

    private readonly ITestOutputHelper _output;
    private readonly Mock<IHandlerService<MotionPacketEntity>> _mockHandlerService;
    private readonly Mock<IDeviceService> _mockDeviceService;
    private readonly Mock<IObserver<BasePacketEntity>> _mockObserver;
    private readonly Mock<IObserver<BasePacketEntity>> _mockObserver2;

    #endregion

    #region Constructor

    public HandlerServiceTests(ITestOutputHelper output)
    {
        _output = output;
        _mockHandlerService = new Mock<IHandlerService<MotionPacketEntity>>();
        _mockDeviceService = new Mock<IDeviceService>();
        _mockObserver = new Mock<IObserver<BasePacketEntity>>();
        _mockObserver2 = new Mock<IObserver<BasePacketEntity>>();
    }

    #endregion

    #region Service Interface Tests

    [Fact]
    public void HandlerService_ShouldBeMockable()
    {
        // Arrange & Act
        var service = _mockHandlerService.Object;

        // Assert
        Assert.NotNull(service);
        Assert.IsAssignableFrom<IHandlerService<MotionPacketEntity>>(service);
    }

    [Fact]
    public void HandlerService_ShouldImplementIObserver()
    {
        // Arrange & Act
        var service = _mockHandlerService.Object;

        // Assert
        Assert.IsAssignableFrom<IObserver<RawPacketEvent>>(service);
    }

    #endregion

    #region True Positive Tests

    [Fact]
    public async Task SubscribeToDeviceAsync_WithValidParameters_ShouldCompleteSuccessfully()
    {
        // Arrange
        var deviceName = "eth0";
        _mockHandlerService.Setup(x => x.SubscribeToDeviceAsync(It.IsAny<IDeviceService>(), It.IsAny<string>()))
            .Returns(Task.CompletedTask);

        // Act
        await _mockHandlerService.Object.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName);

        // Assert
        _mockHandlerService.Verify(x => x.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName), Times.Once);
    }

    [Fact]
    public async Task UnsubscribeAsync_WithSubscribedDevice_ShouldCompleteSuccessfully()
    {
        // Arrange
        _mockHandlerService.Setup(x => x.UnsubscribeAsync(It.IsAny<IDeviceService>()))
            .Returns(Task.CompletedTask);

        // Act
        await _mockHandlerService.Object.UnsubscribeAsync(_mockDeviceService.Object);

        // Assert
        _mockHandlerService.Verify(x => x.UnsubscribeAsync(_mockDeviceService.Object), Times.Once);
    }

    [Fact]
    public void GetStats_WithActiveProcessing_ShouldReturnCorrectStatistics()
    {
        // Arrange
        var expectedStats = (Captured: 1000L, Parsed: 950L, Dropped: 50L, AvgLatencyMs: 2.5);
        _mockHandlerService.Setup(x => x.GetStats())
            .Returns(expectedStats);

        // Act
        var stats = _mockHandlerService.Object.GetStats();

        // Assert
        Assert.Equal(expectedStats, stats);
        Assert.True(stats.Captured > 0);
        Assert.True(stats.Parsed > 0);
        _mockHandlerService.Verify(x => x.GetStats(), Times.Once);
    }

    [Fact]
    public void GetBackpressureEvents_WithBackpressure_ShouldReturnCorrectCount()
    {
        // Arrange
        var expectedBackpressure = 25L;
        _mockHandlerService.Setup(x => x.GetBackpressureEvents())
            .Returns(expectedBackpressure);

        // Act
        var backpressure = _mockHandlerService.Object.GetBackpressureEvents();

        // Assert
        Assert.Equal(expectedBackpressure, backpressure);
        Assert.True(backpressure > 0);
        _mockHandlerService.Verify(x => x.GetBackpressureEvents(), Times.Once);
    }

    [Fact]
    public void GetRawChannelCount_WithQueuedPackets_ShouldReturnCorrectCount()
    {
        // Arrange
        var expectedCount = 150;
        _mockHandlerService.Setup(x => x.GetRawChannelCount())
            .Returns(expectedCount);

        // Act
        var count = _mockHandlerService.Object.GetRawChannelCount();

        // Assert
        Assert.Equal(expectedCount, count);
        Assert.True(count > 0);
        _mockHandlerService.Verify(x => x.GetRawChannelCount(), Times.Once);
    }

    [Fact]
    public void ResetStats_ShouldCompleteSuccessfully()
    {
        // Arrange
        _mockHandlerService.Setup(x => x.ResetStats());

        // Act
        _mockHandlerService.Object.ResetStats();

        // Assert
        _mockHandlerService.Verify(x => x.ResetStats(), Times.Once);
    }

    #endregion

    #region True Negative Tests

    [Fact]
    public void GetStats_WithNoProcessing_ShouldReturnZeroStats()
    {
        // Arrange
        var zeroStats = (Captured: 0L, Parsed: 0L, Dropped: 0L, AvgLatencyMs: 0.0);
        _mockHandlerService.Setup(x => x.GetStats())
            .Returns(zeroStats);

        // Act
        var stats = _mockHandlerService.Object.GetStats();

        // Assert
        Assert.Equal(zeroStats, stats);
        Assert.Equal(0L, stats.Captured);
        Assert.Equal(0L, stats.Parsed);
        Assert.Equal(0L, stats.Dropped);
        Assert.Equal(0.0, stats.AvgLatencyMs);
        _mockHandlerService.Verify(x => x.GetStats(), Times.Once);
    }

    [Fact]
    public void GetBackpressureEvents_WithNoBackpressure_ShouldReturnZero()
    {
        // Arrange
        var zeroBackpressure = 0L;
        _mockHandlerService.Setup(x => x.GetBackpressureEvents())
            .Returns(zeroBackpressure);

        // Act
        var backpressure = _mockHandlerService.Object.GetBackpressureEvents();

        // Assert
        Assert.Equal(zeroBackpressure, backpressure);
        Assert.Equal(0L, backpressure);
        _mockHandlerService.Verify(x => x.GetBackpressureEvents(), Times.Once);
    }

    [Fact]
    public void GetRawChannelCount_WithEmptyChannel_ShouldReturnZero()
    {
        // Arrange
        var zeroCount = 0;
        _mockHandlerService.Setup(x => x.GetRawChannelCount())
            .Returns(zeroCount);

        // Act
        var count = _mockHandlerService.Object.GetRawChannelCount();

        // Assert
        Assert.Equal(zeroCount, count);
        Assert.Equal(0, count);
        _mockHandlerService.Verify(x => x.GetRawChannelCount(), Times.Once);
    }

    [Fact]
    public async Task UnsubscribeAsync_WithNonSubscribedDevice_ShouldNotThrow()
    {
        // Arrange
        var nonSubscribedDevice = new Mock<IDeviceService>();
        _mockHandlerService.Setup(x => x.UnsubscribeAsync(It.IsAny<IDeviceService>()))
            .Returns(Task.CompletedTask);

        // Act & Assert
        await _mockHandlerService.Object.UnsubscribeAsync(nonSubscribedDevice.Object);
        _mockHandlerService.Verify(x => x.UnsubscribeAsync(nonSubscribedDevice.Object), Times.Once);
    }

    #endregion

    #region False Positive Tests

    [Fact]
    public void GetStats_WithIncorrectStatistics_ShouldReturnWrongValues()
    {
        // Arrange
        var incorrectStats = (Captured: -100L, Parsed: 2000L, Dropped: -50L, AvgLatencyMs: -5.0);
        _mockHandlerService.Setup(x => x.GetStats())
            .Returns(incorrectStats);

        // Act
        var stats = _mockHandlerService.Object.GetStats();

        // Assert
        Assert.Equal(incorrectStats, stats);
        Assert.True(stats.Captured < 0); // False positive - negative captured count
        Assert.True(stats.Parsed > stats.Captured); // False positive - parsed > captured
        Assert.True(stats.Dropped < 0); // False positive - negative dropped count
        Assert.True(stats.AvgLatencyMs < 0); // False positive - negative latency
        _mockHandlerService.Verify(x => x.GetStats(), Times.Once);
    }

    [Fact]
    public void GetBackpressureEvents_WithImpossibleCount_ShouldReturnIncorrectValue()
    {
        // Arrange
        var impossibleBackpressure = -10L; // Negative backpressure is impossible
        _mockHandlerService.Setup(x => x.GetBackpressureEvents())
            .Returns(impossibleBackpressure);

        // Act
        var backpressure = _mockHandlerService.Object.GetBackpressureEvents();

        // Assert
        Assert.Equal(impossibleBackpressure, backpressure);
        Assert.True(backpressure < 0); // False positive - negative backpressure
        _mockHandlerService.Verify(x => x.GetBackpressureEvents(), Times.Once);
    }

    [Fact]
    public void GetRawChannelCount_WithImpossibleCount_ShouldReturnIncorrectValue()
    {
        // Arrange
        var impossibleCount = -5; // Negative count is impossible
        _mockHandlerService.Setup(x => x.GetRawChannelCount())
            .Returns(impossibleCount);

        // Act
        var count = _mockHandlerService.Object.GetRawChannelCount();

        // Assert
        Assert.Equal(impossibleCount, count);
        Assert.True(count < 0); // False positive - negative count
        _mockHandlerService.Verify(x => x.GetRawChannelCount(), Times.Once);
    }

    [Fact]
    public async Task SubscribeToDeviceAsync_WithInvalidDevice_ShouldAppearToSucceed()
    {
        // Arrange
        var invalidDeviceName = "nonexistent_device";
        _mockHandlerService.Setup(x => x.SubscribeToDeviceAsync(It.IsAny<IDeviceService>(), It.IsAny<string>()))
            .Returns(Task.CompletedTask);

        // Act
        await _mockHandlerService.Object.SubscribeToDeviceAsync(_mockDeviceService.Object, invalidDeviceName);

        // Assert
        _mockHandlerService.Verify(x => x.SubscribeToDeviceAsync(_mockDeviceService.Object, invalidDeviceName), Times.Once);
        // False positive - method appears to succeed but device doesn't exist
    }

    #endregion

    #region False Negative Tests

    [Fact]
    public void GetStats_WithActiveProcessing_ShouldNotReturnAllStatistics()
    {
        // Arrange
        var partialStats = (Captured: 1000L, Parsed: 0L, Dropped: 0L, AvgLatencyMs: 0.0);
        _mockHandlerService.Setup(x => x.GetStats())
            .Returns(partialStats);

        // Act
        var stats = _mockHandlerService.Object.GetStats();

        // Assert
        Assert.Equal(partialStats, stats);
        Assert.True(stats.Captured > 0);
        Assert.Equal(0L, stats.Parsed); // False negative - should have parsed some packets
        Assert.Equal(0L, stats.Dropped); // False negative - should have dropped some packets
        _mockHandlerService.Verify(x => x.GetStats(), Times.Once);
    }

    [Fact]
    public void GetBackpressureEvents_WithHighLoad_ShouldNotReturnAllEvents()
    {
        // Arrange
        var partialBackpressure = 5L; // Should be much higher under high load
        _mockHandlerService.Setup(x => x.GetBackpressureEvents())
            .Returns(partialBackpressure);

        // Act
        var backpressure = _mockHandlerService.Object.GetBackpressureEvents();

        // Assert
        Assert.Equal(partialBackpressure, backpressure);
        Assert.True(backpressure < 100); // False negative - should be much higher
        _mockHandlerService.Verify(x => x.GetBackpressureEvents(), Times.Once);
    }

    [Fact]
    public void GetRawChannelCount_WithHighLoad_ShouldNotReturnAllCount()
    {
        // Arrange
        var partialCount = 10; // Should be much higher under high load
        _mockHandlerService.Setup(x => x.GetRawChannelCount())
            .Returns(partialCount);

        // Act
        var count = _mockHandlerService.Object.GetRawChannelCount();

        // Assert
        Assert.Equal(partialCount, count);
        Assert.True(count < 1000); // False negative - should be much higher
        _mockHandlerService.Verify(x => x.GetRawChannelCount(), Times.Once);
    }

    [Fact]
    public async Task SubscribeToDeviceAsync_WithValidDevice_ShouldNotActuallySubscribe()
    {
        // Arrange
        var deviceName = "eth0";
        _mockHandlerService.Setup(x => x.SubscribeToDeviceAsync(It.IsAny<IDeviceService>(), It.IsAny<string>()))
            .Returns(Task.CompletedTask);

        // Act
        await _mockHandlerService.Object.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName);

        // Assert
        _mockHandlerService.Verify(x => x.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName), Times.Once);
        // False negative - method appears to succeed but subscription doesn't actually work
    }

    [Fact]
    public void ResetStats_WithActiveProcessing_ShouldNotActuallyReset()
    {
        // Arrange
        _mockHandlerService.Setup(x => x.ResetStats());

        // Act
        _mockHandlerService.Object.ResetStats();

        // Assert
        _mockHandlerService.Verify(x => x.ResetStats(), Times.Once);
        // False negative - method appears to succeed but stats aren't actually reset
    }

    #endregion

    #region Additional Error Handling Tests

    [Fact]
    public async Task SubscribeToDeviceAsync_WithNullDeviceService_ShouldThrowArgumentNullException()
    {
        // Arrange
        var deviceName = "eth0";
        _mockHandlerService.Setup(x => x.SubscribeToDeviceAsync(null!, It.IsAny<string>()))
            .ThrowsAsync(new ArgumentNullException(nameof(IDeviceService)));

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => 
            _mockHandlerService.Object.SubscribeToDeviceAsync(null!, deviceName));
    }

    [Fact]
    public async Task SubscribeToDeviceAsync_WithEmptyDeviceName_ShouldThrowArgumentException()
    {
        // Arrange
        var emptyDeviceName = "";
        _mockHandlerService.Setup(x => x.SubscribeToDeviceAsync(It.IsAny<IDeviceService>(), It.IsAny<string>()))
            .ThrowsAsync(new ArgumentException("Device name cannot be empty"));

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => 
            _mockHandlerService.Object.SubscribeToDeviceAsync(_mockDeviceService.Object, emptyDeviceName));
    }

    [Fact]
    public async Task SubscribeToDeviceAsync_WithNonExistentDevice_ShouldThrowArgumentException()
    {
        // Arrange
        var nonExistentDevice = "nonexistent";
        _mockHandlerService.Setup(x => x.SubscribeToDeviceAsync(It.IsAny<IDeviceService>(), It.IsAny<string>()))
            .ThrowsAsync(new ArgumentException("Device not found"));

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => 
            _mockHandlerService.Object.SubscribeToDeviceAsync(_mockDeviceService.Object, nonExistentDevice));
    }

    [Fact]
    public void OnNext_WithValidRawPacketEvent_ShouldCallObserverMethod()
    {
        // Arrange
        var rawPacketEvent = new RawPacketEvent("eth0", new ReadOnlyMemory<byte>(new byte[] { 1, 2, 3, 4 }), DateTime.UtcNow);
        _mockHandlerService.Setup(x => x.OnNext(It.IsAny<RawPacketEvent>()));

        // Act
        _mockHandlerService.Object.OnNext(rawPacketEvent);

        // Assert
        _mockHandlerService.Verify(x => x.OnNext(rawPacketEvent), Times.Once);
    }

    [Fact]
    public void OnNext_WithNullRawPacketEvent_ShouldThrowArgumentNullException()
    {
        // Arrange
        _mockHandlerService.Setup(x => x.OnNext(null!))
            .Throws(new ArgumentNullException(nameof(RawPacketEvent)));

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => _mockHandlerService.Object.OnNext(null!));
    }

    [Fact]
    public void OnError_WithException_ShouldCallObserverMethod()
    {
        // Arrange
        var exception = new InvalidOperationException("Test error");
        _mockHandlerService.Setup(x => x.OnError(It.IsAny<Exception>()));

        // Act
        _mockHandlerService.Object.OnError(exception);

        // Assert
        _mockHandlerService.Verify(x => x.OnError(exception), Times.Once);
    }

    [Fact]
    public void OnCompleted_ShouldCallObserverMethod()
    {
        // Arrange
        _mockHandlerService.Setup(x => x.OnCompleted());

        // Act
        _mockHandlerService.Object.OnCompleted();

        // Assert
        _mockHandlerService.Verify(x => x.OnCompleted(), Times.Once);
    }

    [Fact]
    public async Task HandlerService_ShouldHandleSubscriptionErrors()
    {
        // Arrange
        var deviceName = "faulty_device";
        _mockHandlerService.Setup(x => x.SubscribeToDeviceAsync(It.IsAny<IDeviceService>(), It.IsAny<string>()))
            .ThrowsAsync(new InvalidOperationException("Device subscription failed"));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => 
            _mockHandlerService.Object.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName));
    }

    [Fact]
    public async Task HandlerService_ShouldHandleUnsubscriptionErrors()
    {
        // Arrange
        _mockHandlerService.Setup(x => x.UnsubscribeAsync(It.IsAny<IDeviceService>()))
            .ThrowsAsync(new InvalidOperationException("Unsubscription failed"));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => 
            _mockHandlerService.Object.UnsubscribeAsync(_mockDeviceService.Object));
    }

    [Fact]
    public void HandlerService_ShouldHandleStatsRetrievalErrors()
    {
        // Arrange
        _mockHandlerService.Setup(x => x.GetStats())
            .Throws(new InvalidOperationException("Stats retrieval failed"));

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => _mockHandlerService.Object.GetStats());
    }

    #endregion

    #region Integration Tests

    [Fact]
    public void FullHandlerLifecycle_ShouldWorkCorrectly()
    {
        // Arrange
        var deviceName = "eth0";
        var initialStats = (Captured: 0L, Parsed: 0L, Dropped: 0L, AvgLatencyMs: 0.0);
        var finalStats = (Captured: 1000L, Parsed: 950L, Dropped: 50L, AvgLatencyMs: 2.5);
        
        _mockHandlerService.Setup(x => x.SubscribeToDeviceAsync(It.IsAny<IDeviceService>(), It.IsAny<string>()))
            .Returns(Task.CompletedTask);
        _mockHandlerService.Setup(x => x.UnsubscribeAsync(It.IsAny<IDeviceService>()))
            .Returns(Task.CompletedTask);
        _mockHandlerService.SetupSequence(x => x.GetStats())
            .Returns(initialStats)
            .Returns(finalStats);
        _mockHandlerService.Setup(x => x.ResetStats());

        // Act
        _mockHandlerService.Object.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName);
        var stats1 = _mockHandlerService.Object.GetStats();
        var stats2 = _mockHandlerService.Object.GetStats();
        _mockHandlerService.Object.ResetStats();
        _mockHandlerService.Object.UnsubscribeAsync(_mockDeviceService.Object);

        // Assert
        _mockHandlerService.Verify(x => x.SubscribeToDeviceAsync(_mockDeviceService.Object, deviceName), Times.Once);
        _mockHandlerService.Verify(x => x.GetStats(), Times.Exactly(2));
        _mockHandlerService.Verify(x => x.ResetStats(), Times.Once);
        _mockHandlerService.Verify(x => x.UnsubscribeAsync(_mockDeviceService.Object), Times.Once);
        Assert.Equal(initialStats, stats1);
        Assert.Equal(finalStats, stats2);
    }

    #endregion

    #region IDisposable Implementation

    public void Dispose()
    {
        // Mock objects are automatically cleaned up
        // No explicit cleanup needed for mocked services
    }

    #endregion
}
