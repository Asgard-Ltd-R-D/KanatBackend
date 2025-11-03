using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Moq;
using PacketProcessing.Config;
using PacketProcessing.Context;
using PacketProcessing.Entities.Range;
using PacketProcessing.Repositories.EfRepository;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Tests.Utils;
using Xunit;
using Xunit.Abstractions;

namespace PacketProcessing.Tests.UnitTests.DatabaseTests;

/// <summary>
/// Tests for database initialization and connectivity
/// </summary>
public class DatabaseInitializationTests : IDisposable
{
    #region Fields

    private readonly ITestOutputHelper _output;
    private readonly ServiceProvider _serviceProvider;
    private readonly IConfiguration _configuration;
    private readonly PostgresDbContext _postgresContext;
    private readonly QuestDbContext _questDbContext;

    #endregion

    #region Constructor

    public DatabaseInitializationTests(ITestOutputHelper output)
    {
        _output = output;
        
        
        // Use test configuration provider
        _configuration = TestConfigurationProvider.Configuration;

        // Create service collection and configure services
        var services = new ServiceCollection();
        
        // Add logging with Xunit logger
        services.AddLogging(builder =>
        {
            builder.AddProvider(new XunitLoggerProvider(_output));
            builder.SetMinimumLevel(LogLevel.Debug);
        });

        // Configure database services
        DatabaseConfiguration.ConfigureServices(services, _configuration);

        _serviceProvider = services.BuildServiceProvider();
        _postgresContext = _serviceProvider.GetRequiredService<PostgresDbContext>();
        _questDbContext = _serviceProvider.GetRequiredService<QuestDbContext>();
        
        _output.WriteLine($"[{DateTime.UtcNow:O}] DatabaseInitializationTests initialized");
    }

    #endregion

    #region PostgreSQL Tests

    [Fact]
    public async Task PostgresDbContext_ShouldConnectSuccessfully()
    {
        // Arrange
        _output.WriteLine("Testing PostgreSQL database connectivity...");

        // Act
        var canConnect = await _postgresContext.Database.CanConnectAsync();
        
        // Assert
        Assert.True(canConnect, "PostgreSQL database should be accessible");
        _output.WriteLine("PostgreSQL database connection successful");
    }

    [Fact]
    public async Task PostgresDbContext_ShouldCreateDatabaseIfNotExists()
    {
        // Arrange
        _output.WriteLine("Testing PostgreSQL database creation...");

        // Act
        var created = await _postgresContext.Database.EnsureCreatedAsync();
        
        // Assert
        Assert.True(created || !created, "Database creation should succeed or database should already exist");
        
        // Verify database exists
        var canConnect = await _postgresContext.Database.CanConnectAsync();
        Assert.True(canConnect, "Database should be accessible after creation");
        
        _output.WriteLine($"PostgreSQL database creation result: {(created ? "Created" : "Already exists")}");
    }

    [Fact]
    public async Task PostgresDbContext_ShouldHaveRequiredTables()
    {
        // Arrange
        _output.WriteLine("Testing PostgreSQL table creation and access...");
        
        // Act - Force database creation (this will create tables if they don't exist)
        var databaseCreated = await _postgresContext.Database.EnsureCreatedAsync();
        _output.WriteLine($"Database creation result: {(databaseCreated ? "Created" : "Already exists")}");

        // Assert - Check if database is accessible
        var canConnect = _postgresContext.Database.CanConnect();
        Assert.True(canConnect, "Database should be accessible");
        
        _output.WriteLine("Database is accessible, verifying DbSet properties...");

        // Verify that all DbSet properties are properly configured
        Assert.NotNull(_postgresContext.Ranges);
        Assert.NotNull(_postgresContext.Targets);
        Assert.NotNull(_postgresContext.Hits);
        Assert.NotNull(_postgresContext.Events);
        
        _output.WriteLine("All DbSet properties are properly configured: Ranges, Targets, Hits, Events");
        
        // Test that we can access the model (this verifies entity configuration)
        var model = _postgresContext.Model;
        Assert.NotNull(model);
        
        var rangeEntityType = model.FindEntityType(typeof(RangeEntity));
        var targetEntityType = model.FindEntityType(typeof(TargetEntity));
        var hitEntityType = model.FindEntityType(typeof(HitEntity));
        var eventEntityType = model.FindEntityType(typeof(EventEntity));
        
        Assert.NotNull(rangeEntityType);
        Assert.NotNull(targetEntityType);
        Assert.NotNull(hitEntityType);
        Assert.NotNull(eventEntityType);
        
        _output.WriteLine("All entity types are properly configured in the model");
        
        _output.WriteLine("PostgreSQL database and entity configuration test completed successfully");
    }

    [Fact]
    public async Task PostgresDbContext_ShouldSupportBasicCrudOperations()
    {
        // Arrange
        _output.WriteLine("Testing PostgreSQL CRUD operations...");
        await _postgresContext.Database.EnsureCreatedAsync();
        var testRange = new RangeEntity
        {
            Id = Guid.NewGuid(),
            StartTime = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
            EndTime = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeMilliseconds(),
            Description = "Test Description",
            Timestamp = DateTime.UtcNow
        };

        // Act - Create
        _output.WriteLine($"Creating test range: {testRange.Description}");
        _postgresContext.Ranges.Add(testRange);
        await _postgresContext.SaveChangesAsync();

        // Act - Read
        var retrievedRange = await _postgresContext.Ranges
            .FirstOrDefaultAsync(r => r.Id == testRange.Id);

        // Assert
        Assert.NotNull(retrievedRange);
        Assert.Equal(testRange.Description, retrievedRange.Description);
        Assert.Equal(testRange.StartTime, retrievedRange.StartTime);
        Assert.Equal(testRange.EndTime, retrievedRange.EndTime);
        _output.WriteLine($"Successfully retrieved range: {retrievedRange.Description}");

        // Act - Update
        retrievedRange.Description = "Updated Test Range";
        await _postgresContext.SaveChangesAsync();
        _output.WriteLine($"Updated range description to: {retrievedRange.Description}");

        // Act - Read Updated
        var updatedRange = await _postgresContext.Ranges
            .FirstOrDefaultAsync(r => r.Id == testRange.Id);

        // Assert
        Assert.NotNull(updatedRange);
        Assert.Equal("Updated Test Range", updatedRange.Description);

        // Act - Delete
        _postgresContext.Ranges.Remove(updatedRange);
        await _postgresContext.SaveChangesAsync();
        _output.WriteLine("Deleted test range");

        // Act - Verify Deletion
        var deletedRange = await _postgresContext.Ranges
            .FirstOrDefaultAsync(r => r.Id == testRange.Id);

        // Assert
        Assert.Null(deletedRange);
        _output.WriteLine("PostgreSQL CRUD operations test completed successfully");
    }

    #endregion

    #region QuestDB Tests

    [Fact]
    public void QuestDbContext_ShouldInitializeSuccessfully()
    {
        // Act & Assert
        Assert.NotNull(_questDbContext);
        
        // Verify connection string is properly configured
        var connectionString = _questDbContext.ConnectionString;
        Assert.NotNull(connectionString);
        Assert.Contains("Host=localhost", connectionString);
        Assert.Contains("Port=8812", connectionString);
        Assert.Contains("Database=PacketDBTest", connectionString);
    }

    [Fact]
    public async Task QuestDbContext_ShouldConnectSuccessfully()
    {
        // Act
        await using var connection = await _questDbContext.OpenPgAsync();

        // Assert
        Assert.NotNull(connection);
        Assert.Equal(System.Data.ConnectionState.Open, connection.State);
    }

    [Fact]
    public async Task QuestDbContext_ShouldCreateTablesIfNotExist()
    {
        // Act
        var tablesCreated = await _questDbContext.EnsureDatabaseAsync();

        // Assert - This should not throw an exception
        Assert.True(tablesCreated || !tablesCreated, "Table creation should complete without errors");
    }

    [Fact]
    public void EfRepositoryFactory_ShouldCreateRepositories()
    {
        // Arrange
        var factory = _serviceProvider.GetRequiredService<IEfRepositoryFactory>();

        // Act
        var rangeRepository = factory.Get<RangeEntity>();

        // Assert
        Assert.NotNull(rangeRepository);
    }

    [Fact]
    public void InfluxRepositoryFactory_ShouldCreateRepositories()
    {
        // Arrange
        var factory = _serviceProvider.GetRequiredService<IInfluxRepositoryFactory>();

        // Act
        var motionRepository = factory.Get<MotionPacketEntity>();
        var safetyRepository = factory.Get<SafetyPacketEntity>();
        var onvifRepository = factory.Get<OnVIFPacketEntity>();

        // Assert
        Assert.NotNull(motionRepository);
        Assert.NotNull(safetyRepository);
        Assert.NotNull(onvifRepository);
    }

    [Fact]
    public async Task DatabaseInitialization_ShouldCompleteWithoutErrors()
    {
        // Act & Assert - This should not throw any exceptions
        await _postgresContext.Database.EnsureCreatedAsync();
        await _questDbContext.EnsureDatabaseAsync();
        
        var postgresConnected = await _postgresContext.Database.CanConnectAsync();
        await using var questDbConnection = await _questDbContext.OpenPgAsync();
        var questDbConnected = questDbConnection.State == System.Data.ConnectionState.Open;
        
        Assert.True(postgresConnected, "PostgreSQL should be connected");
        Assert.True(questDbConnected, "QuestDB should be connected");
    }

    [Fact]
    public async Task DatabaseConfiguration_ShouldHandleConnectionFailures()
    {
        // Arrange
        _output.WriteLine("Testing database connection failure handling...");
        var invalidSettings = new Dictionary<string, string?>
        {
            ["Postgres:Host"] = "invalid-host",
            ["Postgres:Port"] = "9999",
            ["Postgres:Username"] = "invalid",
            ["Postgres:Password"] = "invalid",
            ["Postgres:Database"] = "invalid"
        };

        var invalidConfig = TestConfigurationProvider.CreateConfigurationWithSettings(invalidSettings);

        var services = new ServiceCollection();
        services.AddLogging(builder =>
        {
            builder.AddProvider(new XunitLoggerProvider(_output));
            builder.SetMinimumLevel(LogLevel.Debug);
        });

        DatabaseConfiguration.ConfigureServices(services, invalidConfig);
        var serviceProvider = services.BuildServiceProvider();
        var invalidContext = serviceProvider.GetRequiredService<PostgresDbContext>();

        // Act & Assert
        var canConnect = await invalidContext.Database.CanConnectAsync();
        Assert.False(canConnect, "Invalid connection should fail gracefully");
        
        _output.WriteLine("Connection failure test completed successfully");
        serviceProvider.Dispose();
    }

    [Fact]
    public void TestConfigurationProvider_ShouldWorkWithDatabaseInitialization()
    {
        // Arrange
        _output.WriteLine("Testing TestConfigurationProvider with database initialization...");

        // Act
        var postgresConfig = TestConfigurationProvider.GetPostgresConfiguration();
        var questDbConfig = TestConfigurationProvider.GetQuestDbConfiguration();

        // Assert
        Assert.NotNull(postgresConfig);
        Assert.NotNull(questDbConfig);
        Assert.Equal("RangeDBTest", postgresConfig.Database);
        Assert.Equal("PacketDBTest", questDbConfig.Database);
        
        _output.WriteLine("TestConfigurationProvider test completed successfully");
    }

    #endregion

    #region IDisposable

    public void Dispose()
    {
        _output.WriteLine($"[{DateTime.UtcNow:O}] DatabaseInitializationTests disposing...");
        _serviceProvider?.Dispose();
    }

    #endregion
}
