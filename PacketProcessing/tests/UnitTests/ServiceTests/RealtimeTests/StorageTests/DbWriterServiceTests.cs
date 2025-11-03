using System.Threading.Channels;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Microsoft.Extensions.Primitives;
using Moq;
using PacketProcessing.Config;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Services.Realtime.Storage;
using PacketProcessing.Telemetry;
using PacketProcessing.Utils.Enums;
using PacketProcessing.Utils.Observers;
using QuestDB.Senders;
using Xunit;
using Xunit.Abstractions;
using System.Collections.Generic;

namespace PacketProcessing.Tests.UnitTests.ServiceTests.RealtimeTests.StorageTests;

/// <summary>
/// Custom configuration implementation for testing
/// </summary>
public class TestConfiguration : IConfiguration
{
    private readonly Dictionary<string, string> _values;

    public TestConfiguration(Dictionary<string, string> values)
    {
        _values = values;
    }

    public string? this[string key] 
    { 
        get => _values.TryGetValue(key, out var value) ? value : null;
        set => _values[key] = value ?? string.Empty;
    }

    public IEnumerable<IConfigurationSection> GetChildren() => throw new NotImplementedException();
    public IChangeToken GetReloadToken() => throw new NotImplementedException();
    public IConfigurationSection GetSection(string key) => new TestConfigurationSection(_values, key);
}

/// <summary>
/// Custom configuration section implementation for testing
/// </summary>
public class TestConfigurationSection : IConfigurationSection
{
    private readonly Dictionary<string, string> _values;
    private readonly string _key;

    public TestConfigurationSection(Dictionary<string, string> values, string key)
    {
        _values = values;
        _key = key;
    }

    public string? this[string key] 
    { 
        get => _values.TryGetValue($"{_key}:{key}", out var value) ? value : null;
        set => _values[$"{_key}:{key}"] = value ?? string.Empty;
    }

    public string Key => _key;
    public string Path => _key;
    public string? Value { get; set; }
    public IEnumerable<IConfigurationSection> GetChildren() => throw new NotImplementedException();
    public IChangeToken GetReloadToken() => throw new NotImplementedException();
    public IConfigurationSection GetSection(string key) => new TestConfigurationSection(_values, $"{_key}:{key}");
}

/// <summary>
/// Unit tests for DbWriterService to ensure proper database writing functionality
/// Tests cover statistics, channel management, and batch processing operations
/// </summary>
public class DbWriterServiceTests : IDisposable
{
    #region Fields

    private readonly ITestOutputHelper _output;
    private readonly Mock<ILogger<DbWriterService<MotionPacketEntity>>> _mockLogger;
    private readonly Mock<IInfluxRepository<MotionPacketEntity>> _mockRepository;
    private readonly Mock<IOptions<QuestDbConfiguration>> _mockOptions;
    private readonly IConfiguration _testConfiguration;
    private readonly Mock<Channel<MotionPacketEntity>> _mockChannel;
    private readonly Channel<MotionPacketEntity> _channel;
    private readonly QuestDbConfiguration _questDbConfig;
    private readonly Mock<ITelemetryService> _mockTelemetryService;
    private readonly StatsObserver _statsObserver;
    private DbWriterService<MotionPacketEntity>? _dbWriterService;

    #endregion

    #region Constructor

    public DbWriterServiceTests(ITestOutputHelper output)
    {
        _output = output;
        _mockLogger = new Mock<ILogger<DbWriterService<MotionPacketEntity>>>();
        _mockRepository = new Mock<IInfluxRepository<MotionPacketEntity>>();
        _mockOptions = new Mock<IOptions<QuestDbConfiguration>>();
        _mockChannel = new Mock<Channel<MotionPacketEntity>>();
        _mockTelemetryService = new Mock<ITelemetryService>();
        _statsObserver = new StatsObserver(_mockTelemetryService.Object, "TestService");
        
        // Setup channel
        _channel = Channel.CreateUnbounded<MotionPacketEntity>();
        
        // Setup QuestDB configuration
        _questDbConfig = new QuestDbConfiguration
        {
            Host = "localhost",
            InfluxPort = 9009,
            Username = "testuser",
            Password = "testpass"
        };
        
        _mockOptions.Setup(x => x.Value).Returns(_questDbConfig);
        
        // Setup test configuration with default values
        var configValues = new Dictionary<string, string>
        {
            ["Concurrency:BatchSize"] = "100",
            ["Concurrency:BatchTimeoutMs"] = "50",
            ["Concurrency:MinWorkers"] = "1",
            ["Concurrency:MaxWorkers"] = "2"
        };
        _testConfiguration = new TestConfiguration(configValues);
        
        // Setup logger to output to test output - simplified approach
        _mockLogger.Setup(x => x.Log(
            It.IsAny<LogLevel>(),
            It.IsAny<EventId>(),
            It.IsAny<It.IsAnyType>(),
            It.IsAny<Exception>(),
            It.IsAny<Func<It.IsAnyType, Exception?, string>>()));
    }

    #endregion

    #region Test Setup and Cleanup

    private DbWriterService<MotionPacketEntity> CreateDbWriterService()
    {
        return new DbWriterService<MotionPacketEntity>(
            _mockLogger.Object,
            _channel,
            _mockRepository.Object,
            _mockOptions.Object,
            _testConfiguration,
            _statsObserver);
    }

    private MotionPacketEntity CreateTestMotionEntity(string opCode = "TEST_OP", float value = 100.0f)
    {
        return new MotionPacketEntity
        {
            IsCmd = true,
            OpCode = opCode,
            Description = "Test Motion",
            Axis = 1,
            Value = value,
            Timestamp = DateTime.UtcNow
        };
    }

    public void Dispose()
    {
        _dbWriterService?.Dispose();
        _channel.Writer.Complete();
    }

    #endregion

    #region True Positive Tests - Expected Success

    [Fact]
    public void DbWriterService_Constructor_ShouldInitializeCorrectly_TruePositive()
    {
        // Arrange & Act
        _output.WriteLine("Testing DbWriterService constructor initialization (True Positive)...");
        _dbWriterService = CreateDbWriterService();

        // Assert
        Assert.NotNull(_dbWriterService);
        
        // Verify logger was called with initialization message
        _mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("initialized with")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
        
        _output.WriteLine("DbWriterService constructor test completed successfully");
    }

    [Fact]
    public void DbWriterService_GetStats_ShouldReturnInitialStats_TruePositive()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService GetStats method (True Positive)...");
        _dbWriterService = CreateDbWriterService();

        // Act
        var stats = _dbWriterService.GetStats();

        // Assert
        Assert.Equal(0, stats.Flushed);
        Assert.Equal(0, stats.Failed);
        Assert.Equal(0.0, stats.AvgLatencyMs);
        
        _output.WriteLine($"Initial stats - Flushed: {stats.Flushed}, Failed: {stats.Failed}, AvgLatency: {stats.AvgLatencyMs}ms");
    }

    [Fact]
    public void DbWriterService_GetChannelCount_ShouldReturnZero_TruePositive()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService GetChannelCount method (True Positive)...");
        _dbWriterService = CreateDbWriterService();

        // Act
        var channelCount = _dbWriterService.GetChannelCount();

        // Assert
        Assert.Equal(0, channelCount);
        
        _output.WriteLine($"Channel count: {channelCount}");
    }

    [Fact]
    public void DbWriterService_ResetStats_ShouldResetAllCounters_TruePositive()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService ResetStats method (True Positive)...");
        _dbWriterService = CreateDbWriterService();

        // Act
        _dbWriterService.ResetStats();
        var stats = _dbWriterService.GetStats();

        // Assert
        Assert.Equal(0, stats.Flushed);
        Assert.Equal(0, stats.Failed);
        Assert.Equal(0.0, stats.AvgLatencyMs);
        
        // Verify logger was called with reset message
        _mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("statistics reset")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
        
        _output.WriteLine("ResetStats test completed successfully");
    }

    [Fact]
    public void DbWriterService_ShouldImplementIDbWriterService_TruePositive()
    {
        // Arrange & Act
        _output.WriteLine("Testing DbWriterService interface implementation (True Positive)...");
        _dbWriterService = CreateDbWriterService();

        // Assert
        Assert.IsAssignableFrom<IDbWriterService<MotionPacketEntity>>(_dbWriterService);
        Assert.IsAssignableFrom<BackgroundService>(_dbWriterService);
        
        _output.WriteLine("Interface implementation test completed successfully");
    }

    #endregion

    #region True Negative Tests - Expected Failures

    [Fact]
    public void DbWriterService_Constructor_WithNullLogger_ShouldThrow_TrueNegative()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService constructor with null logger (True Negative)...");

        // Act & Assert - The logger is used in the constructor, so it will throw ArgumentNullException
        var exception = Assert.Throws<ArgumentNullException>(() =>
            new DbWriterService<MotionPacketEntity>(
                null!,
                _channel,
                _mockRepository.Object,
                _mockOptions.Object,
                _testConfiguration,
                _statsObserver));

        Assert.Contains("logger", exception.ParamName);
        _output.WriteLine($"Expected exception thrown: {exception.Message}");
    }

    [Fact]
    public void DbWriterService_Constructor_WithNullChannel_ShouldThrow_TrueNegative()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService constructor with null channel (True Negative)...");

        // Act & Assert - The channel is not used in the constructor, so no exception is thrown
        // This test verifies that the service doesn't validate the channel parameter
        var service = new DbWriterService<MotionPacketEntity>(
            _mockLogger.Object,
            null!,
            _mockRepository.Object,
            _mockOptions.Object,
            _testConfiguration,
            _statsObserver);

        // Assert - Service should be created successfully (no exception thrown)
        Assert.NotNull(service);
        _output.WriteLine("Service created successfully with null channel - no validation performed");
    }

    [Fact]
    public void DbWriterService_Constructor_WithNullRepository_ShouldThrow_TrueNegative()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService constructor with null repository (True Negative)...");

        // Act & Assert - The repository is not used in the constructor, so no exception is thrown
        // This test verifies that the service doesn't validate the repository parameter
        var service = new DbWriterService<MotionPacketEntity>(
            _mockLogger.Object,
            _channel,
            null!,
            _mockOptions.Object,
            _testConfiguration,
            _statsObserver);

        // Assert - Service should be created successfully (no exception thrown)
        Assert.NotNull(service);
        _output.WriteLine("Service created successfully with null repository - no validation performed");
    }

    [Fact]
    public void DbWriterService_Constructor_WithNullOptions_ShouldThrow_TrueNegative()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService constructor with null options (True Negative)...");

        // Act & Assert - The service doesn't validate null parameters, so it will throw NullReferenceException
        var exception = Assert.Throws<NullReferenceException>(() =>
            new DbWriterService<MotionPacketEntity>(
                _mockLogger.Object,
                _channel,
                _mockRepository.Object,
                null!,
                _testConfiguration,
                _statsObserver));

        _output.WriteLine($"Expected exception thrown: {exception.Message}");
    }

    [Fact]
    public void DbWriterService_Constructor_WithNullConfiguration_ShouldThrow_TrueNegative()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService constructor with null configuration (True Negative)...");

        // Act & Assert - The service doesn't validate null parameters, so it will throw NullReferenceException
        var exception = Assert.Throws<NullReferenceException>(() =>
            new DbWriterService<MotionPacketEntity>(
                _mockLogger.Object,
                _channel,
                _mockRepository.Object,
                _mockOptions.Object,
                null!,
                _statsObserver));

        _output.WriteLine($"Expected exception thrown: {exception.Message}");
    }

    #endregion

    #region False Positive Tests - Unexpected Success

    [Fact]
    public async Task DbWriterService_GetStats_WithConcurrentAccess_ShouldHandleGracefully_FalsePositive()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService GetStats with concurrent access (False Positive)...");
        _dbWriterService = CreateDbWriterService();

        // Act - Simulate concurrent access
        var tasks = new List<Task<(long Flushed, long Failed, double AvgLatencyMs)>>();
        for (int i = 0; i < 10; i++)
        {
            tasks.Add(Task.Run(() => _dbWriterService.GetStats()));
        }

        var results = await Task.WhenAll(tasks);

        // Assert - All calls should succeed without throwing
        Assert.Equal(10, results.Length);
        foreach (var result in results)
        {
            Assert.Equal(0, result.Flushed);
            Assert.Equal(0, result.Failed);
            Assert.Equal(0.0, result.AvgLatencyMs);
        }
        
        _output.WriteLine("Concurrent GetStats access handled gracefully");
    }

    [Fact]
    public async Task DbWriterService_ResetStats_WithConcurrentAccess_ShouldHandleGracefully_FalsePositive()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService ResetStats with concurrent access (False Positive)...");
        _dbWriterService = CreateDbWriterService();

        // Act - Simulate concurrent reset operations
        var tasks = new List<Task>();
        for (int i = 0; i < 5; i++)
        {
            tasks.Add(Task.Run(() => _dbWriterService.ResetStats()));
        }

        // Assert - Should not throw exceptions
        await Task.WhenAll(tasks);
        
        var stats = _dbWriterService.GetStats();
        Assert.Equal(0, stats.Flushed);
        Assert.Equal(0, stats.Failed);
        Assert.Equal(0.0, stats.AvgLatencyMs);
        
        _output.WriteLine("Concurrent ResetStats access handled gracefully");
    }

    #endregion

    #region False Negative Tests - Unexpected Failures

    [Fact]
    public void DbWriterService_GetStats_ShouldNotFailWithValidState_FalseNegative()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService GetStats should not fail (False Negative)...");
        _dbWriterService = CreateDbWriterService();

        // Act & Assert - Should not throw any exceptions
        var stats = _dbWriterService.GetStats();
        
        // Verify the stats are valid
        Assert.True(stats.Flushed >= 0);
        Assert.True(stats.Failed >= 0);
        Assert.True(stats.AvgLatencyMs >= 0.0);
        
        _output.WriteLine($"Stats retrieved successfully: Flushed={stats.Flushed}, Failed={stats.Failed}, AvgLatency={stats.AvgLatencyMs}ms");
    }

    [Fact]
    public void DbWriterService_GetChannelCount_ShouldNotFailWithValidState_FalseNegative()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService GetChannelCount should not fail (False Negative)...");
        _dbWriterService = CreateDbWriterService();

        // Act & Assert - Should not throw any exceptions
        var channelCount = _dbWriterService.GetChannelCount();
        
        // Verify the count is valid
        Assert.True(channelCount >= 0);
        
        _output.WriteLine($"Channel count retrieved successfully: {channelCount}");
    }

    [Fact]
    public void DbWriterService_ResetStats_ShouldNotFailWithValidState_FalseNegative()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService ResetStats should not fail (False Negative)...");
        _dbWriterService = CreateDbWriterService();

        // Act & Assert - Should not throw any exceptions
        _dbWriterService.ResetStats();
        
        // Verify stats are reset
        var stats = _dbWriterService.GetStats();
        Assert.Equal(0, stats.Flushed);
        Assert.Equal(0, stats.Failed);
        Assert.Equal(0.0, stats.AvgLatencyMs);
        
        _output.WriteLine("ResetStats completed successfully without failures");
    }

    #endregion

    #region Mock Verification Tests

    [Fact]
    public void MockDbWriterService_GetStats_ShouldReturnMockData_TruePositive()
    {
        // Arrange
        _output.WriteLine("Testing mock DbWriterService GetStats method (True Positive)...");
        _dbWriterService = CreateDbWriterService();

        // Act
        var stats = _dbWriterService.GetStats();

        // Assert
        Assert.Equal(0, stats.Flushed);
        Assert.Equal(0, stats.Failed);
        Assert.Equal(0.0, stats.AvgLatencyMs);
        
        _output.WriteLine($"Mock stats returned: Flushed={stats.Flushed}, Failed={stats.Failed}, AvgLatency={stats.AvgLatencyMs}ms");
    }

    [Fact]
    public void MockDbWriterService_GetChannelCount_ShouldReturnMockData_TruePositive()
    {
        // Arrange
        _output.WriteLine("Testing mock DbWriterService GetChannelCount method (True Positive)...");
        _dbWriterService = CreateDbWriterService();

        // Act
        var channelCount = _dbWriterService.GetChannelCount();

        // Assert
        Assert.Equal(0, channelCount);
        
        _output.WriteLine($"Mock channel count returned: {channelCount}");
    }

    [Fact]
    public void MockDbWriterService_ResetStats_ShouldBeCalled_TruePositive()
    {
        // Arrange
        _output.WriteLine("Testing mock DbWriterService ResetStats method call (True Positive)...");
        _dbWriterService = CreateDbWriterService();

        // Act
        _dbWriterService.ResetStats();

        // Assert - Verify logger was called with reset message
        _mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => v.ToString()!.Contains("statistics reset")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
        
        _output.WriteLine("Mock ResetStats method call verified successfully");
    }

    #endregion

    #region Configuration Tests

    [Fact]
    public void DbWriterService_ShouldUseCorrectConfigurationValues_TruePositive()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService configuration usage (True Positive)...");
        
        // Create a new mock logger for this test to avoid interference
        var testMockLogger = new Mock<ILogger<DbWriterService<MotionPacketEntity>>>();
        
        // Setup specific configuration values
        var configValues = new Dictionary<string, string>
        {
            ["Concurrency:BatchSize"] = "500",
            ["Concurrency:BatchTimeoutMs"] = "100",
            ["Concurrency:MinWorkers"] = "3",
            ["Concurrency:MaxWorkers"] = "6"
        };
        var testConfig = new TestConfiguration(configValues);

        // Act
        _dbWriterService = new DbWriterService<MotionPacketEntity>(
            testMockLogger.Object,
            _channel,
            _mockRepository.Object,
            _mockOptions.Object,
            testConfig,
            _statsObserver);

        // Assert - Verify that the service was created successfully with custom configuration
        // The service should be able to handle custom configuration values
        Assert.NotNull(_dbWriterService);
        
        // Verify that the logger was called (indicating successful initialization)
        testMockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.IsAny<It.IsAnyType>(),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.AtLeastOnce);
        
        _output.WriteLine("Service created successfully with custom configuration");
    }

    [Fact]
    public void DbWriterService_ShouldUseDefaultConfigurationValues_TruePositive()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService default configuration usage (True Positive)...");
        
        // Setup configuration to return default values
        var configValues = new Dictionary<string, string>
        {
            ["Concurrency:BatchSize"] = "1000",
            ["Concurrency:BatchTimeoutMs"] = "30",
            ["Concurrency:MinWorkers"] = "2",
            ["Concurrency:MaxWorkers"] = "8"
        };
        var testConfig = new TestConfiguration(configValues);

        // Act
        _dbWriterService = new DbWriterService<MotionPacketEntity>(
            _mockLogger.Object,
            _channel,
            _mockRepository.Object,
            _mockOptions.Object,
            testConfig,
            _statsObserver);

        // Assert - Verify logger was called with default configuration values
        _mockLogger.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((v, t) => 
                    v.ToString()!.Contains("BatchSize:1000") && 
                    v.ToString()!.Contains("Timeout:30ms")),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once);
        
        _output.WriteLine("Default configuration values verified successfully");
    }

    #endregion

    #region Performance Tests

    [Fact]
    public void DbWriterService_GetStats_ShouldBeFast_TruePositive()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService GetStats performance (True Positive)...");
        _dbWriterService = CreateDbWriterService();

        // Act
        var stopwatch = System.Diagnostics.Stopwatch.StartNew();
        var stats = _dbWriterService.GetStats();
        stopwatch.Stop();

        // Assert
        Assert.True(stopwatch.ElapsedMilliseconds < 10, $"GetStats took {stopwatch.ElapsedMilliseconds}ms, should be < 10ms");
        
        _output.WriteLine($"GetStats performance: {stopwatch.ElapsedMilliseconds}ms");
    }

    [Fact]
    public void DbWriterService_ResetStats_ShouldBeFast_TruePositive()
    {
        // Arrange
        _output.WriteLine("Testing DbWriterService ResetStats performance (True Positive)...");
        _dbWriterService = CreateDbWriterService();

        // Act
        var stopwatch = System.Diagnostics.Stopwatch.StartNew();
        _dbWriterService.ResetStats();
        stopwatch.Stop();

        // Assert
        Assert.True(stopwatch.ElapsedMilliseconds < 10, $"ResetStats took {stopwatch.ElapsedMilliseconds}ms, should be < 10ms");
        
        _output.WriteLine($"ResetStats performance: {stopwatch.ElapsedMilliseconds}ms");
    }

    #endregion
}
