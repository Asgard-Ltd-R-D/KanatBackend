using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using PacketProcessing.Config;
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
        var passed = connectionString == expectedConnectionString;
        
        TestResultLogger.LogTestResult(
            "PostgresConfiguration_GetConnectionString_ShouldReturnValidConnectionString",
            passed,
            "PostgresConfiguration with custom values",
            expectedConnectionString,
            connectionString
        );
        
        Assert.Equal(expectedConnectionString, connectionString);
    }

    [Fact]
    public void PostgresConfiguration_GetConnectionString_ShouldUseDefaultValues()
    {
        // Arrange
        var config = new PostgresConfiguration();

        // Act
        var connectionString = config.GetConnectionString();

        // Assert
        var expectedConnectionString = "Host=localhost;Port=5432;Database=pdb;Username=postgres;Password=postgres;Include Error Detail=true;";
        var passed = connectionString == expectedConnectionString;
        
        TestResultLogger.LogTestResult(
            "PostgresConfiguration_GetConnectionString_ShouldUseDefaultValues",
            passed,
            "Default PostgresConfiguration",
            expectedConnectionString,
            connectionString
        );
        
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
        var passed = connectionString == expectedConnectionString;
        
        TestResultLogger.LogTestResult(
            "QuestDbConfiguration_GetPostgresConnectionString_ShouldReturnValidConnectionString",
            passed,
            "QuestDbConfiguration with custom values",
            expectedConnectionString,
            connectionString
        );
        
        Assert.Equal(expectedConnectionString, connectionString);
    }

    [Fact]
    public void QuestDbConfiguration_GetInfluxConnectionString_ShouldReturnValidConnectionString()
    {
        // Arrange
        var config = new QuestDbConfiguration
        {
            Host = "questhost",
            InfluxPort = 9001
        };

        // Act
        var connectionString = config.GetInfluxConnectionString();

        // Assert
        var expectedConnectionString = "http://questhost:9001";
        var passed = connectionString == expectedConnectionString;
        
        TestResultLogger.LogTestResult(
            "QuestDbConfiguration_GetInfluxConnectionString_ShouldReturnValidConnectionString",
            passed,
            "QuestDbConfiguration with custom InfluxPort",
            expectedConnectionString,
            connectionString
        );
        
        Assert.Equal(expectedConnectionString, connectionString);
    }

    [Fact]
    public void QuestDbConfiguration_GetHttpConnectionString_ShouldReturnValidConnectionString()
    {
        // Arrange
        var config = new QuestDbConfiguration
        {
            Host = "questhost",
            HttpPort = 8813
        };

        // Act
        var connectionString = config.GetHttpConnectionString();

        // Assert
        var expectedConnectionString = "http://questhost:8813";
        var passed = connectionString == expectedConnectionString;
        
        TestResultLogger.LogTestResult(
            "QuestDbConfiguration_GetHttpConnectionString_ShouldReturnValidConnectionString",
            passed,
            "QuestDbConfiguration with custom HttpPort",
            expectedConnectionString,
            connectionString
        );
        
        Assert.Equal(expectedConnectionString, connectionString);
    }

    [Fact]
    public void GeneralDatabaseSettings_ShouldHaveCorrectDefaultValues()
    {
        // Arrange & Act
        var settings = new GeneralDatabaseSettings();

        // Assert
        var passed = settings.EnableAutoInitialization && 
                    settings.EnableMigrations && 
                    settings.EnableDetailedLogging && 
                    settings.MaxRetryAttempts == 3 && 
                    settings.RetryDelaySeconds == 5;
        
        TestResultLogger.LogTestResult(
            "GeneralDatabaseSettings_ShouldHaveCorrectDefaultValues",
            passed,
            "Default GeneralDatabaseSettings",
            "All default values should be correct",
            $"AutoInit={settings.EnableAutoInitialization}, Migrations={settings.EnableMigrations}, Logging={settings.EnableDetailedLogging}, Retries={settings.MaxRetryAttempts}, Delay={settings.RetryDelaySeconds}"
        );
        
        Assert.True(settings.EnableAutoInitialization);
        Assert.True(settings.EnableMigrations);
        Assert.True(settings.EnableDetailedLogging);
        Assert.Equal(3, settings.MaxRetryAttempts);
        Assert.Equal(5, settings.RetryDelaySeconds);
    }

    [Fact]
    public void DatabaseConfiguration_ShouldInitializeWithDefaultValues()
    {
        // Arrange & Act
        var config = new DatabaseConfiguration();

        // Assert
        var passed = config.Postgres != null && 
                    config.QuestDb != null && 
                    config.General != null;
        
        TestResultLogger.LogTestResult(
            "DatabaseConfiguration_ShouldInitializeWithDefaultValues",
            passed,
            "New DatabaseConfiguration instance",
            "All properties should be initialized",
            $"Postgres={config.Postgres != null}, QuestDb={config.QuestDb != null}, General={config.General != null}"
        );
        
        Assert.NotNull(config.Postgres!);
        Assert.NotNull(config.QuestDb!);
        Assert.NotNull(config.General!);
    }

    [Fact]
    public void DatabaseConfiguration_ConfigureServices_ShouldNotThrowWithValidConfiguration()
    {
        // Arrange
        var services = new ServiceCollection();
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
                {"QuestDb:Host", "localhost"},
                {"QuestDb:PostgresPort", "8812"},
                {"QuestDb:Database", "qdb"},
                {"QuestDb:Username", "quest"},
                {"QuestDb:Password", "quest"}
            }.Cast<KeyValuePair<string, string?>>())
            .Build();

        // Act & Assert
        var exception = Record.Exception(() => DatabaseConfiguration.ConfigureServices(services, configuration));
        
        var passed = exception == null;
        
        TestResultLogger.LogTestResult(
            "DatabaseConfiguration_ConfigureServices_ShouldNotThrowWithValidConfiguration",
            passed,
            "Valid configuration with all required settings",
            "No exception thrown",
            exception?.Message ?? "No exception"
        );
        
        Assert.Null(exception);
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
        
        TestResultLogger.LogTestResult(
            "DatabaseConfiguration_ConfigureServices_ShouldThrowWithMissingQuestDbConnectionString",
            exception != null,
            "Configuration missing QuestDb connection string",
            "InvalidOperationException thrown",
            exception?.Message ?? "Unknown error"
        );
        
        Assert.NotNull(exception.Message);
        var message = exception.Message!;
        Assert.Contains("QuestDB connection string not found", message);
    }
}
