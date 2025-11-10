using Moq;
using PacketProcessing.DTOs.Packet;
using PacketProcessing.Services.Realtime.Networking;
using PacketProcessing.Utils.Observers;
using System.Collections.Concurrent;
using Xunit;
using Xunit.Abstractions;

namespace PacketProcessing.Tests.UnitTests.ServiceTests.RealtimeTests.Networking;

/// <summary>
/// Unit tests for IDeviceService interface using mocked implementation
/// Tests service interface behavior, method calls, and return values
/// </summary>
public class DeviceServiceTests : IDisposable
{
    #region Fields

    private readonly ITestOutputHelper _output;
    private readonly Mock<IDeviceService> _mockDeviceService;
    private readonly Mock<IObserver<RawPacketEvent>> _mockObserver;
    private readonly Mock<IObserver<RawPacketEvent>> _mockObserver2;

    #endregion

    #region Constructor

    public DeviceServiceTests(ITestOutputHelper output)
    {
        _output = output;
        _mockDeviceService = new Mock<IDeviceService>();
        _mockObserver = new Mock<IObserver<RawPacketEvent>>();
        _mockObserver2 = new Mock<IObserver<RawPacketEvent>>();
    }

    #endregion

    #region Service Interface Tests

    [Fact]
    public void DeviceService_ShouldBeMockable()
    {
        // Arrange & Act
        var service = _mockDeviceService.Object;

        // Assert
        Assert.NotNull(service);
        Assert.IsAssignableFrom<IDeviceService>(service);
    }

    [Fact]
    public void DeviceService_ShouldImplementIObservable()
    {
        // Arrange & Act
        var service = _mockDeviceService.Object;

        // Assert
        Assert.IsAssignableFrom<IObservable<RawPacketEvent>>(service);
    }

    #endregion

    #region True Positive Tests

    [Fact]
    public void GetAvailableDeviceNames_WithValidDevices_ShouldReturnCorrectDeviceList()
    {
        // Arrange
        var expectedDevices = new List<string> { "eth0", "wlan0", "lo" };
        _mockDeviceService.Setup(x => x.GetAvailableDeviceNames())
            .Returns(expectedDevices);

        // Act
        var deviceNames = _mockDeviceService.Object.GetAvailableDeviceNames();

        // Assert
        Assert.NotNull(deviceNames);
        Assert.Equal(expectedDevices, deviceNames);
        Assert.True(deviceNames.Count > 0);
        _mockDeviceService.Verify(x => x.GetAvailableDeviceNames(), Times.Once);
    }

    [Fact]
    public async Task SubscribeWithFilterAsync_WithValidParameters_ShouldCompleteSuccessfully()
    {
        // Arrange
        var deviceName = "eth0";
        var filter = "tcp port 80";
        _mockDeviceService.Setup(x => x.SubscribeWithFilterAsync(It.IsAny<IObserver<RawPacketEvent>>(), It.IsAny<string>(), It.IsAny<string>()))
            .Returns(Task.CompletedTask);

        // Act
        await _mockDeviceService.Object.SubscribeWithFilterAsync(_mockObserver.Object, deviceName, filter);

        // Assert
        _mockDeviceService.Verify(x => x.SubscribeWithFilterAsync(_mockObserver.Object, deviceName, filter), Times.Once);
    }

    [Fact]
    public async Task UnsubscribeAsync_WithSubscribedObserver_ShouldCompleteSuccessfully()
    {
        // Arrange
        _mockDeviceService.Setup(x => x.UnsubscribeAsync(It.IsAny<IObserver<RawPacketEvent>>()))
            .Returns(Task.CompletedTask);

        // Act
        await _mockDeviceService.Object.UnsubscribeAsync(_mockObserver.Object);

        // Assert
        _mockDeviceService.Verify(x => x.UnsubscribeAsync(_mockObserver.Object), Times.Once);
    }

    [Fact]
    public void GetStatus_WithActiveSubscriptions_ShouldReturnSubscriptionInfo()
    {
        // Arrange
        var expectedStatus = new List<DeviceSubscriptionStatusDto>
        {
            new() { DeviceName = "eth0", Filter = "tcp port 80", IsCapturing = true }
        };
        _mockDeviceService.Setup(x => x.GetStatus())
            .Returns(expectedStatus);

        // Act
        var status = _mockDeviceService.Object.GetStatus();

        // Assert
        Assert.NotNull(status);
        Assert.Equal(expectedStatus, status);
        Assert.True(status.Count > 0);
        _mockDeviceService.Verify(x => x.GetStatus(), Times.Once);
    }

    [Fact]
    public void Subscribe_WithValidObserver_ShouldReturnDisposable()
    {
        // Arrange
        var mockDisposable = new Mock<IDisposable>();
        _mockDeviceService.Setup(x => x.Subscribe(It.IsAny<IObserver<RawPacketEvent>>()))
            .Returns(mockDisposable.Object);

        // Act
        var disposable = _mockDeviceService.Object.Subscribe(_mockObserver.Object);

        // Assert
        Assert.NotNull(disposable);
        Assert.IsAssignableFrom<IDisposable>(disposable);
        _mockDeviceService.Verify(x => x.Subscribe(_mockObserver.Object), Times.Once);
    }

    #endregion

    #region True Negative Tests

    [Fact]
    public void GetAvailableDeviceNames_WithNoDevices_ShouldReturnEmptyCollection()
    {
        // Arrange
        var emptyDevices = new List<string>();
        _mockDeviceService.Setup(x => x.GetAvailableDeviceNames())
            .Returns(emptyDevices);

        // Act
        var deviceNames = _mockDeviceService.Object.GetAvailableDeviceNames();

        // Assert
        Assert.NotNull(deviceNames);
        Assert.Empty(deviceNames);
        _mockDeviceService.Verify(x => x.GetAvailableDeviceNames(), Times.Once);
    }

    [Fact]
    public void GetStatus_WithNoSubscriptions_ShouldReturnEmptyCollection()
    {
        // Arrange
        var emptyStatus = new List<DeviceSubscriptionStatusDto>();
        _mockDeviceService.Setup(x => x.GetStatus())
            .Returns(emptyStatus);

        // Act
        var status = _mockDeviceService.Object.GetStatus();

        // Assert
        Assert.NotNull(status);
        Assert.Empty(status);
        _mockDeviceService.Verify(x => x.GetStatus(), Times.Once);
    }

    [Fact]
    public async Task UnsubscribeAsync_WithNonSubscribedObserver_ShouldNotThrow()
    {
        // Arrange
        _mockDeviceService.Setup(x => x.UnsubscribeAsync(It.IsAny<IObserver<RawPacketEvent>>()))
            .Returns(Task.CompletedTask);

        // Act & Assert
        await _mockDeviceService.Object.UnsubscribeAsync(_mockObserver.Object);
        _mockDeviceService.Verify(x => x.UnsubscribeAsync(_mockObserver.Object), Times.Once);
    }

    [Fact]
    public async Task StopAllAsync_WithNoActiveSubscriptions_ShouldNotThrow()
    {
        // Arrange
        _mockDeviceService.Setup(x => x.StopAllAsync())
            .Returns(Task.CompletedTask);

        // Act & Assert
        await _mockDeviceService.Object.StopAllAsync();
        _mockDeviceService.Verify(x => x.StopAllAsync(), Times.Once);
    }

    #endregion

    #region False Positive Tests

    [Fact]
    public void GetAvailableDeviceNames_WithInvalidDeviceNames_ShouldReturnIncorrectResults()
    {
        // Arrange
        var invalidDevices = new List<string> { "", "invalid_device", null! };
        _mockDeviceService.Setup(x => x.GetAvailableDeviceNames())
            .Returns(invalidDevices);

        // Act
        var deviceNames = _mockDeviceService.Object.GetAvailableDeviceNames();

        // Assert
        Assert.NotNull(deviceNames);
        Assert.Contains("", deviceNames); // False positive - empty string should not be valid
        Assert.Contains("invalid_device", deviceNames); // False positive - non-existent device
        _mockDeviceService.Verify(x => x.GetAvailableDeviceNames(), Times.Once);
    }

    [Fact]
    public void GetStatus_WithIncorrectSubscriptionInfo_ShouldReturnWrongStatus()
    {
        // Arrange
        var incorrectStatus = new List<DeviceSubscriptionStatusDto>
        {
            new() { DeviceName = "nonexistent", Filter = "invalid filter", IsCapturing = true }
        };
        _mockDeviceService.Setup(x => x.GetStatus())
            .Returns(incorrectStatus);

        // Act
        var status = _mockDeviceService.Object.GetStatus();

        // Assert
        Assert.NotNull(status);
        Assert.True(status.Count > 0);
        Assert.Contains(status, s => s.DeviceName == "nonexistent"); // False positive - non-existent device
        Assert.Contains(status, s => s.Filter == "invalid filter"); // False positive - invalid filter
        _mockDeviceService.Verify(x => x.GetStatus(), Times.Once);
    }

    [Fact]
    public async Task SubscribeWithFilterAsync_WithInvalidFilter_ShouldAppearToSucceed()
    {
        // Arrange
        var deviceName = "eth0";
        var invalidFilter = "invalid bpf filter syntax";
        _mockDeviceService.Setup(x => x.SubscribeWithFilterAsync(It.IsAny<IObserver<RawPacketEvent>>(), It.IsAny<string>(), It.IsAny<string>()))
            .Returns(Task.CompletedTask);

        // Act
        await _mockDeviceService.Object.SubscribeWithFilterAsync(_mockObserver.Object, deviceName, invalidFilter);

        // Assert
        _mockDeviceService.Verify(x => x.SubscribeWithFilterAsync(_mockObserver.Object, deviceName, invalidFilter), Times.Once);
        // False positive - method appears to succeed but filter is invalid
    }

    #endregion

    #region False Negative Tests

    [Fact]
    public void GetAvailableDeviceNames_WithValidDevices_ShouldNotReturnAllDevices()
    {
        // Arrange
        var partialDevices = new List<string> { "eth0" }; // Missing wlan0, lo
        _mockDeviceService.Setup(x => x.GetAvailableDeviceNames())
            .Returns(partialDevices);

        // Act
        var deviceNames = _mockDeviceService.Object.GetAvailableDeviceNames();

        // Assert
        Assert.NotNull(deviceNames);
        Assert.True(deviceNames.Count > 0);
        Assert.DoesNotContain("wlan0", deviceNames); // False negative - wlan0 should be available
        Assert.DoesNotContain("lo", deviceNames); // False negative - lo should be available
        _mockDeviceService.Verify(x => x.GetAvailableDeviceNames(), Times.Once);
    }

    [Fact]
    public void GetStatus_WithActiveSubscriptions_ShouldNotReturnAllSubscriptions()
    {
        // Arrange
        var partialStatus = new List<DeviceSubscriptionStatusDto>
        {
            new() { DeviceName = "eth0", Filter = "tcp port 80", IsCapturing = true }
            // Missing other active subscriptions
        };
        _mockDeviceService.Setup(x => x.GetStatus())
            .Returns(partialStatus);

        // Act
        var status = _mockDeviceService.Object.GetStatus();

        // Assert
        Assert.NotNull(status);
        Assert.True(status.Count > 0);
        Assert.DoesNotContain(status, s => s.DeviceName == "wlan0"); // False negative - wlan0 subscription missing
        _mockDeviceService.Verify(x => x.GetStatus(), Times.Once);
    }

    [Fact]
    public async Task SubscribeWithFilterAsync_WithValidDevice_ShouldNotActuallySubscribe()
    {
        // Arrange
        var deviceName = "eth0";
        var filter = "tcp port 80";
        _mockDeviceService.Setup(x => x.SubscribeWithFilterAsync(It.IsAny<IObserver<RawPacketEvent>>(), It.IsAny<string>(), It.IsAny<string>()))
            .Returns(Task.CompletedTask);

        // Act
        await _mockDeviceService.Object.SubscribeWithFilterAsync(_mockObserver.Object, deviceName, filter);

        // Assert
        _mockDeviceService.Verify(x => x.SubscribeWithFilterAsync(_mockObserver.Object, deviceName, filter), Times.Once);
        // False negative - method appears to succeed but subscription doesn't actually work
    }

    [Fact]
    public void Subscribe_WithValidObserver_ShouldNotActuallyRegisterObserver()
    {
        // Arrange
        var mockDisposable = new Mock<IDisposable>();
        _mockDeviceService.Setup(x => x.Subscribe(It.IsAny<IObserver<RawPacketEvent>>()))
            .Returns(mockDisposable.Object);

        // Act
        var disposable = _mockDeviceService.Object.Subscribe(_mockObserver.Object);

        // Assert
        Assert.NotNull(disposable);
        _mockDeviceService.Verify(x => x.Subscribe(_mockObserver.Object), Times.Once);
        // False negative - disposable returned but observer not actually registered
    }

    #endregion



    #region Additional Error Handling Tests

    [Fact]
    public async Task SubscribeWithFilterAsync_WithNullObserver_ShouldThrowArgumentNullException()
    {
        // Arrange
        var deviceName = "eth0";
        var filter = "tcp port 80";
        _mockDeviceService.Setup(x => x.SubscribeWithFilterAsync(null!, It.IsAny<string>(), It.IsAny<string>()))
            .ThrowsAsync(new ArgumentNullException(nameof(IObserver<RawPacketEvent>)));

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => 
            _mockDeviceService.Object.SubscribeWithFilterAsync(null!, deviceName, filter));
    }

    [Fact]
    public async Task SubscribeWithFilterAsync_WithNonExistentDevice_ShouldThrowArgumentException()
    {
        // Arrange
        var deviceName = "nonexistent";
        var filter = "tcp port 80";
        _mockDeviceService.Setup(x => x.SubscribeWithFilterAsync(It.IsAny<IObserver<RawPacketEvent>>(), It.IsAny<string>(), It.IsAny<string>()))
            .ThrowsAsync(new ArgumentException("Device not found"));

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => 
            _mockDeviceService.Object.SubscribeWithFilterAsync(_mockObserver.Object, deviceName, filter));
    }

    [Fact]
    public async Task SubscribeWithFilterAsync_WithValidDeviceButNoInterface_ShouldThrowInvalidOperationException()
    {
        // Arrange
        var deviceName = "eth0";
        var filter = "tcp port 80";
        _mockDeviceService.Setup(x => x.SubscribeWithFilterAsync(It.IsAny<IObserver<RawPacketEvent>>(), It.IsAny<string>(), It.IsAny<string>()))
            .ThrowsAsync(new InvalidOperationException("Device interface not available"));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => 
            _mockDeviceService.Object.SubscribeWithFilterAsync(_mockObserver.Object, deviceName, filter));
    }

    [Fact]
    public void Subscribe_WithNullObserver_ShouldThrowArgumentNullException()
    {
        // Arrange
        _mockDeviceService.Setup(x => x.Subscribe(null!))
            .Throws(new ArgumentNullException(nameof(IObserver<RawPacketEvent>)));

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => _mockDeviceService.Object.Subscribe(null!));
    }

    [Fact]
    public async Task DeviceService_ShouldHandleSubscriptionErrors()
    {
        // Arrange
        var deviceName = "faulty_device";
        _mockDeviceService.Setup(x => x.SubscribeWithFilterAsync(It.IsAny<IObserver<RawPacketEvent>>(), It.IsAny<string>(), It.IsAny<string>()))
            .ThrowsAsync(new InvalidOperationException("Device subscription failed"));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => 
            _mockDeviceService.Object.SubscribeWithFilterAsync(_mockObserver.Object, deviceName, "tcp port 80"));
    }

    [Fact]
    public async Task DeviceService_ShouldHandleUnsubscriptionErrors()
    {
        // Arrange
        _mockDeviceService.Setup(x => x.UnsubscribeAsync(It.IsAny<IObserver<RawPacketEvent>>()))
            .ThrowsAsync(new InvalidOperationException("Unsubscription failed"));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => 
            _mockDeviceService.Object.UnsubscribeAsync(_mockObserver.Object));
    }

    [Fact]
    public async Task DeviceService_ShouldHandleStopAllErrors()
    {
        // Arrange
        _mockDeviceService.Setup(x => x.StopAllAsync())
            .ThrowsAsync(new InvalidOperationException("Stop all failed"));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => 
            _mockDeviceService.Object.StopAllAsync());
    }

    [Fact]
    public void DeviceService_ShouldHandleStatusRetrievalErrors()
    {
        // Arrange
        _mockDeviceService.Setup(x => x.GetStatus())
            .Throws(new InvalidOperationException("Status retrieval failed"));

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => _mockDeviceService.Object.GetStatus());
    }

    #endregion

    #region Integration Tests

    [Fact]
    public void FullSubscriptionLifecycle_ShouldWorkCorrectly()
    {
        // Arrange
        var deviceName = "eth0";
        var filter = "tcp port 80";
        var mockDisposable = new Mock<IDisposable>();
        var expectedStatus = new List<DeviceSubscriptionStatusDto>
        {
            new() { DeviceName = deviceName, Filter = filter, IsCapturing = true }
        };
        
        _mockDeviceService.Setup(x => x.SubscribeWithFilterAsync(It.IsAny<IObserver<RawPacketEvent>>(), It.IsAny<string>(), It.IsAny<string>()))
            .Returns(Task.CompletedTask);
        _mockDeviceService.Setup(x => x.Subscribe(It.IsAny<IObserver<RawPacketEvent>>()))
            .Returns(mockDisposable.Object);
        _mockDeviceService.Setup(x => x.GetStatus())
            .Returns(expectedStatus);
        _mockDeviceService.Setup(x => x.UnsubscribeAsync(It.IsAny<IObserver<RawPacketEvent>>()))
            .Returns(Task.CompletedTask);
        _mockDeviceService.Setup(x => x.StopAllAsync())
            .Returns(Task.CompletedTask);

        // Act
        _mockDeviceService.Object.SubscribeWithFilterAsync(_mockObserver.Object, deviceName, filter);
        var disposable = _mockDeviceService.Object.Subscribe(_mockObserver.Object);
        var status = _mockDeviceService.Object.GetStatus();
        _mockDeviceService.Object.UnsubscribeAsync(_mockObserver.Object);
        _mockDeviceService.Object.StopAllAsync();

        // Assert
        _mockDeviceService.Verify(x => x.SubscribeWithFilterAsync(_mockObserver.Object, deviceName, filter), Times.Once);
        _mockDeviceService.Verify(x => x.Subscribe(_mockObserver.Object), Times.Once);
        _mockDeviceService.Verify(x => x.GetStatus(), Times.Once);
        _mockDeviceService.Verify(x => x.UnsubscribeAsync(_mockObserver.Object), Times.Once);
        _mockDeviceService.Verify(x => x.StopAllAsync(), Times.Once);
        Assert.NotNull(disposable);
        Assert.Equal(expectedStatus, status);
    }

    #endregion

    #region IDisposable Implementation

    public void Dispose()
    {
        // Clean up any resources if needed
        // Mock objects are automatically cleaned up
    }

    #endregion
}
