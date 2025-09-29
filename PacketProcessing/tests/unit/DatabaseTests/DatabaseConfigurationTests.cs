using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using PacketProcessing.Config;
using PacketProcessing.Context;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Tests;
using Xunit;

namespace PacketProcessing.Tests.unit.DatabaseTests;

/// <summary>
/// Tests for DatabaseConfiguration class
/// </summary>
public class DatabaseConfigurationTests
{
    [Fact]
    public void PostgresConfiguration_GetConnectionString_ShouldReturnValidConnectionString()
    {
        // Arrange
        var config = new PostgresConfiguration
        {
            Host = "testhost",
            Port = 5433,
            Database = "testdb",
            Username = "testuser",
            Password = "testpass"
        };

        // Act
        var connectionString = config.GetConnectionString();

        // Assert
        var expectedConnectionString = "Host=testhost;Port=5433;Database=testdb;Username=testuser;Password=testpass;Include Error Detail=true;";
        Assert.Equal(expectedConnectionString, connectionString);
    }

    [Fact]
    public void QuestDbConfiguration_GetPostgresConnectionString_ShouldReturnValidConnectionString()
    {
        // Arrange
        var config = new QuestDbConfiguration
        {
            Host = "questhost",
            PostgresPort = 9010,
            Database = "questdb",
            Username = "questuser",
            Password = "questpass"
        };

        // Act
        var connectionString = config.GetPostgresConnectionString();

        // Assert
        var expectedConnectionString = "Host=questhost;Port=9010;Database=questdb;Username=questuser;Password=questpass;Include Error Detail=true;";
        Assert.Equal(expectedConnectionString, connectionString);
    }

    [Fact]
    public void DatabaseConfiguration_ConfigureServices_ShouldRegisterAllServices()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddLogging();
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string>
            {
                {"ConnectionStrings:Postgres", "Host=localhost;Port=56432;Database=pdb;Username=postgres;Password=postgres;"},
                {"ConnectionStrings:QuestDb", "Host=localhost;Port=9009;Database=qdb;Username=quest;Password=quest;"},
                {"Postgres:Host", "localhost"},
                {"Postgres:Port", "56432"},
                {"Postgres:Database", "pdb"},
                {"Postgres:Username", "postgres"},
                {"Postgres:Password", "postgres"},
                {"QuestDb:PgHost", "localhost"},
                {"QuestDb:PgPort", "8812"},
                {"QuestDb:Database", "qdb"},
                {"QuestDb:PgUser", "quest"},
                {"QuestDb:PgPassword", "quest"}
            }.Cast<KeyValuePair<string, string?>>())
            .Build();

        // Act & Assert
        var exception = Record.Exception(() => DatabaseConfiguration.ConfigureServices(services, configuration));
        Assert.Null(exception);

        var serviceProvider = services.BuildServiceProvider();
        
        // Verify key services are registered
        Assert.NotNull(serviceProvider.GetService<QuestDbContext>());
        Assert.NotNull(serviceProvider.GetService<IInfluxRepository<MotionPacketEntity>>());
        Assert.NotNull(serviceProvider.GetService<IInfluxRepository<OnVIFPacketEntity>>());
        Assert.NotNull(serviceProvider.GetService<IInfluxRepository<SafetyPacketEntity>>());
    }

    [Fact]
    public void DatabaseConfiguration_ConfigureServices_ShouldThrowWithMissingQuestDbConnectionString()
    {
        // Arrange
        var services = new ServiceCollection();
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string>
            {
                {"ConnectionStrings:Postgres", "Host=localhost;Port=5432;Database=test;Username=test;Password=test;"},
                {"Postgres:Host", "localhost"},
                {"Postgres:Port", "5432"},
                {"Postgres:Database", "test"},
                {"Postgres:Username", "test"},
                {"Postgres:Password", "test"}
                // Missing QuestDb connection string
            }.Cast<KeyValuePair<string, string?>>())
            .Build();

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => 
            DatabaseConfiguration.ConfigureServices(services, configuration));
        
        Assert.Contains("QuestDB connection string not found", exception.Message);
    }
}
