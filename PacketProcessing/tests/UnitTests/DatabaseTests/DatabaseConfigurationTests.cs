using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Moq;
using PacketProcessing.Config;
using PacketProcessing.Context;
using PacketProcessing.Entities.Range;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories.EfRepository;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Tests.Utils;
using Xunit;
using Xunit.Abstractions;

namespace PacketProcessing.Tests.UnitTests.DatabaseTests;

/// <summary>
/// Tests for database configuration and context initialization
/// </summary>
public class DatabaseConfigurationTests : IDisposable
{
    #region Fields

    private readonly ITestOutputHelper _output;
    private readonly ServiceProvider _serviceProvider;
    private readonly IConfiguration _configuration;

    #endregion

    #region Constructor

    public DatabaseConfigurationTests(ITestOutputHelper output)
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
        
        _output.WriteLine($"[{DateTime.UtcNow:O}] DatabaseConfigurationTests initialized");
    }

    #endregion

    #region Configuration Tests

    [Fact]
    public void Configuration_ShouldLoadPostgresSettings()
    {
        // Arrange
        _output.WriteLine("Testing PostgreSQL configuration loading...");

        // Act
        var postgresConfig = TestConfigurationProvider.GetPostgresConfiguration();

        // Assert
        Assert.NotNull(postgresConfig);
        Assert.Equal("localhost", postgresConfig.Host);
        Assert.Equal(5432, postgresConfig.Port);
        Assert.Equal("postgres", postgresConfig.Username);
        Assert.Equal("postgres", postgresConfig.Password);
        Assert.Equal("RangeDBTest", postgresConfig.Database);
        
        _output.WriteLine($"PostgreSQL configuration loaded successfully: {postgresConfig.Host}:{postgresConfig.Port}/{postgresConfig.Database}");
    }

    [Fact]
    public void Configuration_ShouldLoadQuestDbSettings()
    {
        // Arrange
        _output.WriteLine("Testing QuestDB configuration loading...");

        // Act
        var questDbConfig = TestConfigurationProvider.GetQuestDbConfiguration();

        // Assert
        Assert.NotNull(questDbConfig);
        Assert.Equal("localhost", questDbConfig.Host);
        Assert.Equal(8812, questDbConfig.PostgresPort);
        Assert.Equal(9000, questDbConfig.InfluxPort);
        Assert.Equal(9009, questDbConfig.HttpPort);
        Assert.Equal("quest", questDbConfig.Username);
        Assert.Equal("quest", questDbConfig.Password);
        Assert.Equal("PacketDBTest", questDbConfig.Database);
        
        _output.WriteLine($"QuestDB configuration loaded successfully: {questDbConfig.Host}:{questDbConfig.PostgresPort}/{questDbConfig.Database}");
    }

    [Fact]
    public void PostgresConfiguration_ShouldGenerateValidConnectionString()
    {
        // Arrange
        _output.WriteLine("Testing PostgreSQL connection string generation...");
        var postgresConfig = TestConfigurationProvider.GetPostgresConfiguration();

        // Act
        var connectionString = postgresConfig.GetConnectionString();

        // Assert
        Assert.NotNull(connectionString);
        Assert.Contains("Host=localhost", connectionString);
        Assert.Contains("Port=5432", connectionString);
        Assert.Contains("Database=RangeDBTest", connectionString);
        Assert.Contains("Username=postgres", connectionString);
        Assert.Contains("Password=postgres", connectionString);
        Assert.Contains("Include Error Detail=true", connectionString);
        
        _output.WriteLine($"PostgreSQL connection string generated: {connectionString.Replace("Password=postgres", "Password=***")}");
    }

    [Fact]
    public void QuestDbConfiguration_ShouldGenerateValidConnectionString()
    {
        // Arrange
        _output.WriteLine("Testing QuestDB connection string generation...");
        var questDbConfig = TestConfigurationProvider.GetQuestDbConfiguration();

        // Act
        var connectionString = questDbConfig.GetPostgresConnectionString();

        // Assert
        Assert.NotNull(connectionString);
        Assert.Contains("Host=localhost", connectionString);
        Assert.Contains("Port=8812", connectionString);
        Assert.Contains("Database=PacketDBTest", connectionString);
        Assert.Contains("Username=quest", connectionString);
        Assert.Contains("Password=quest", connectionString);
        Assert.Contains("Include Error Detail=true", connectionString);
        
        _output.WriteLine($"QuestDB connection string generated: {connectionString.Replace("Password=quest", "Password=***")}");
    }

    #endregion

    #region Service Registration Tests

    [Fact]
    public void ServiceCollection_ShouldRegisterPostgresDbContext()
    {
        // Arrange
        _output.WriteLine("Testing PostgreSQL DbContext service registration...");

        // Act
        var postgresContext = _serviceProvider.GetService<PostgresDbContext>();

        // Assert
        Assert.NotNull(postgresContext);
        _output.WriteLine("PostgreSQL DbContext successfully registered and resolved");
    }

    [Fact]
    public void ServiceCollection_ShouldRegisterQuestDbContext()
    {
        // Arrange
        _output.WriteLine("Testing QuestDB DbContext service registration...");

        // Act
        var questDbContext = _serviceProvider.GetService<QuestDbContext>();

        // Assert
        Assert.NotNull(questDbContext);
        _output.WriteLine("QuestDB DbContext successfully registered and resolved");
    }

    [Fact]
    public void ServiceCollection_ShouldRegisterEfRepositoryFactory()
    {
        // Arrange
        _output.WriteLine("Testing EF Repository Factory service registration...");

        // Act
        var efRepositoryFactory = _serviceProvider.GetService<IEfRepositoryFactory>();

        // Assert
        Assert.NotNull(efRepositoryFactory);
        _output.WriteLine("EF Repository Factory successfully registered and resolved");
    }

    [Fact]
    public void ServiceCollection_ShouldRegisterInfluxRepositoryFactory()
    {
        // Arrange
        _output.WriteLine("Testing Influx Repository Factory service registration...");

        // Act
        var influxRepositoryFactory = _serviceProvider.GetService<IInfluxRepositoryFactory>();

        // Assert
        Assert.NotNull(influxRepositoryFactory);
        _output.WriteLine("Influx Repository Factory successfully registered and resolved");
    }

    #endregion

    #region Mock Tests

    [Fact]
    public void MockConfiguration_ShouldWorkWithDatabaseConfiguration()
    {
        // Arrange
        _output.WriteLine("Testing mock configuration with database configuration...");
        var customSettings = new Dictionary<string, string?>
        {
            ["Postgres:Host"] = "mock-host",
            ["Postgres:Port"] = "5432",
            ["Postgres:Username"] = "mock-user",
            ["Postgres:Password"] = "mock-pass",
            ["Postgres:Database"] = "mock-db"
        };

        var mockConfig = TestConfigurationProvider.CreateConfigurationWithSettings(customSettings);

        // Act
        var postgresConfig = mockConfig.GetSection("Postgres").Get<PostgresConfiguration>();

        // Assert
        Assert.NotNull(postgresConfig);
        Assert.Equal("mock-host", postgresConfig.Host);
        Assert.Equal(5432, postgresConfig.Port);
        Assert.Equal("mock-user", postgresConfig.Username);
        Assert.Equal("mock-pass", postgresConfig.Password);
        Assert.Equal("mock-db", postgresConfig.Database);
        
        _output.WriteLine("Mock configuration test completed successfully");
    }


    [Fact]
    public void TestConfigurationProvider_ShouldCreateCustomConfiguration()
    {
        // Arrange
        _output.WriteLine("Testing custom configuration creation...");
        var customSettings = new Dictionary<string, string?>
        {
            ["Postgres:Host"] = "custom-host",
            ["Postgres:Port"] = "9999",
            ["Postgres:Database"] = "custom-db"
        };

        // Act
        var customConfig = TestConfigurationProvider.CreateConfigurationWithSettings(customSettings);
        var postgresConfig = customConfig.GetSection("Postgres").Get<PostgresConfiguration>();

        // Assert
        Assert.NotNull(postgresConfig);
        Assert.Equal("custom-host", postgresConfig.Host);
        Assert.Equal(9999, postgresConfig.Port);
        Assert.Equal("custom-db", postgresConfig.Database);
        
        _output.WriteLine("Custom configuration test completed successfully");
    }

    #endregion

    #region IDisposable

    public void Dispose()
    {
        _output.WriteLine($"[{DateTime.UtcNow:O}] DatabaseConfigurationTests disposing...");
        _serviceProvider?.Dispose();
    }

    #endregion
}
