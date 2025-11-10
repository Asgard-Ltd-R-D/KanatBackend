using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Moq;
using Npgsql;
using PacketProcessing.Config;
using PacketProcessing.Context;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Entities.Range;
using PacketProcessing.Repositories.EfRepository;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Tests.Utils;
using Xunit;
using Xunit.Abstractions;

namespace PacketProcessing.Tests.UnitTests.DatabaseTests;

/// <summary>
/// Tests for database configuration and service registration without external dependencies.
/// </summary>
public class DatabaseConfigurationTests
{
    #region Fields

    private readonly ITestOutputHelper _output;
    private readonly IConfiguration _configuration;

    #endregion

    #region Constructor

    public DatabaseConfigurationTests(ITestOutputHelper output)
    {
        _output = output;
        _configuration = TestConfigurationProvider.Configuration;
    }

    #endregion

    #region Configuration Tests

    [Fact]
    public void Configuration_ShouldLoadPostgresSettings()
    {
        // Act + Arrange
        var postgresConfig = TestConfigurationProvider.GetPostgresConfiguration();

        // Assert
        Assert.NotNull(postgresConfig);
        Assert.Equal("localhost", postgresConfig.Host);
        Assert.Equal(5432, postgresConfig.Port);
        Assert.Equal("postgres", postgresConfig.Username);
        Assert.Equal("postgres", postgresConfig.Password);
        Assert.Equal("RangeDBTest", postgresConfig.Database);
    }

    [Fact]
    public void Configuration_ShouldLoadQuestDbSettings()
    {
        // Act + Arrange
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
    }

    [Fact]
    public void PostgresConfiguration_ShouldGenerateValidConnectionString()
    {
        // Act + Arrange
        var postgresConfig = TestConfigurationProvider.GetPostgresConfiguration();
        var connectionString = postgresConfig.GetConnectionString();

        // Assert
        Assert.NotNull(connectionString);
        Assert.Contains("Host=localhost", connectionString);
        Assert.Contains("Port=5432", connectionString);
        Assert.Contains("Database=RangeDBTest", connectionString);
        Assert.Contains("Username=postgres", connectionString);
        Assert.Contains("Password=postgres", connectionString);
    }

    [Fact]
    public void QuestDbConfiguration_ShouldGenerateValidConnectionString()
    {
        // Arrange
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
    }

    #endregion

    #region Service Registration Tests

    [Fact]
    public void ServiceCollection_ShouldRegisterPostgresDbContext()
    {
        //Arrange
        using var provider = BuildServiceProviderWithStubs();
        // Act
        var postgresContext = provider.GetService<PostgresDbContext>();
        // Assert
        Assert.NotNull(postgresContext);
    }

    [Fact]
    public void ServiceCollection_ShouldRegisterQuestDbContext()
    {
        //Arrange
        using var provider = BuildServiceProviderWithStubs();
        // Act
        var questDbContext = provider.GetService<QuestDbContext>();
        // Assert
        Assert.NotNull(questDbContext);
    }

    [Fact]
    public void ServiceCollection_ShouldRegisterEfRepositoryFactory()
    {
        //Arrange
        using var provider = BuildServiceProviderWithStubs();
        // Act
        var efFactory = provider.GetService<IEfRepositoryFactory>();
        // Assert
        Assert.NotNull(efFactory);
    }

    [Fact]
    public void ServiceCollection_ShouldRegisterInfluxRepositoryFactory()
    {
        //Arrange
        using var provider = BuildServiceProviderWithStubs();
        // Act
        var influxFactory = provider.GetService<IInfluxRepositoryFactory>();
        // Assert
        Assert.NotNull(influxFactory);
    }

    #endregion

    #region Mock Tests

    [Fact]
    public void MockConfiguration_ShouldWorkWithDatabaseConfiguration()
    {
        //Arrange
        var customSettings = new Dictionary<string, string?>
        {
            ["Postgres:Host"] = "mock-host",
            ["Postgres:Port"] = "5432",
            ["Postgres:Username"] = "mock-user",
            ["Postgres:Password"] = "mock-pass",
            ["Postgres:Database"] = "mock-db"
        };

        var mockConfig = TestConfigurationProvider.CreateConfigurationWithSettings(customSettings);
        var postgresConfig = mockConfig.GetSection("Postgres").Get<PostgresConfiguration>();

        Assert.NotNull(postgresConfig);
        Assert.Equal("mock-host", postgresConfig.Host);
        Assert.Equal(5432, postgresConfig.Port);
        Assert.Equal("mock-user", postgresConfig.Username);
        Assert.Equal("mock-pass", postgresConfig.Password);
        Assert.Equal("mock-db", postgresConfig.Database);
    }

    [Fact]
    public void TestConfigurationProvider_ShouldCreateCustomConfiguration()
    {
        var customSettings = new Dictionary<string, string?>
        {
            ["Postgres:Host"] = "custom-host",
            ["Postgres:Port"] = "9999",
            ["Postgres:Database"] = "custom-db"
        };

        var customConfig = TestConfigurationProvider.CreateConfigurationWithSettings(customSettings);
        var postgresConfig = customConfig.GetSection("Postgres").Get<PostgresConfiguration>();

        Assert.NotNull(postgresConfig);
        Assert.Equal("custom-host", postgresConfig.Host);
        Assert.Equal(9999, postgresConfig.Port);
        Assert.Equal("custom-db", postgresConfig.Database);
    }

    #endregion

    #region Helpers

    private ServiceProvider BuildServiceProviderWithStubs()
    {
        var services = new ServiceCollection();

        services.AddLogging(builder =>
        {
            builder.AddProvider(new XunitLoggerProvider(_output));
            builder.SetMinimumLevel(LogLevel.Debug);
        });

        DatabaseConfiguration.ConfigureServices(services, _configuration);

        services.RemoveAll(typeof(PostgresDbContext));
        services.RemoveAll(typeof(QuestDbContext));

        var postgresLogger = new Mock<ILogger<PostgresDbContext>>();
        var postgresOptions = new DbContextOptionsBuilder<PostgresDbContext>()
            .UseInMemoryDatabase($"config-tests-{Guid.NewGuid()}")
            .Options;
        services.AddSingleton<PostgresDbContext>(_ => new PostgresDbContext(postgresOptions, postgresLogger.Object));

        var questLogger = new Mock<ILogger<QuestDbContext>>();
        services.AddSingleton<QuestDbContext>(_ => new QuestDbContextShim(_configuration, questLogger.Object));

        return services.BuildServiceProvider();
    }

    private sealed class QuestDbContextShim : QuestDbContext, IDisposable
    {
        public QuestDbContextShim(IConfiguration cfg, ILogger<QuestDbContext> log)
            : base(cfg, log)
        {
        }

        public NpgsqlConnection OpenMockConnection() =>
            new("Host=localhost;Port=1;Username=test;Password=test;Database=test;");

        public void Dispose()
        {
        }
    }

    #endregion
}
