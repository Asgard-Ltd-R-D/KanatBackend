using PacketProcessing.Config;
using PacketProcessing.Tests;
using Xunit;

namespace PacketProcessing.Tests.unit;

/// <summary>
/// Tests for configuration classes
/// </summary>
public class ConfigurationTests
{
    [Fact]
    public void PostgresOptions_GetConnectionString_ShouldReturnValidConnectionString()
    {
        // Arrange
        var options = new PostgresOptions
        {
            Host = "test-host",
            Port = 5433,
            Database = "test-db",
            Username = "test-user",
            Password = "test-pass"
        };

        // Act
        var connectionString = options.GetConnectionString();

        // Assert
        var containsHost = connectionString.Contains("Host=test-host");
        var containsPort = connectionString.Contains("Port=5433");
        var containsDatabase = connectionString.Contains("Database=test-db");
        var containsUsername = connectionString.Contains("Username=test-user");
        var containsPassword = connectionString.Contains("Password=test-pass");
        
        var passed = containsHost && containsPort && containsDatabase && containsUsername && containsPassword;
        
        TestResultLogger.LogTestResult(
            "PostgresOptions_GetConnectionString_ShouldReturnValidConnectionString",
            passed,
            $"Host={options.Host}, Port={options.Port}, Database={options.Database}",
            "Contains all expected connection string parameters",
            $"Length={connectionString.Length}, Host={containsHost}, Port={containsPort}, Database={containsDatabase}, Username={containsUsername}, Password={containsPassword}"
        );

        Assert.Contains("Host=test-host", connectionString);
        Assert.Contains("Port=5433", connectionString);
        Assert.Contains("Database=test-db", connectionString);
        Assert.Contains("Username=test-user", connectionString);
        Assert.Contains("Password=test-pass", connectionString);
    }

    [Fact]
    public void PostgresOptions_GetConnectionString_ShouldUseDefaultValues()
    {
        // Arrange
        var options = new PostgresOptions();

        // Act
        var connectionString = options.GetConnectionString();

        // Assert
        var containsDefaultHost = connectionString.Contains("Host=localhost");
        var containsDefaultPort = connectionString.Contains("Port=5432");
        
        var passed = containsDefaultHost && containsDefaultPort;
        
        TestResultLogger.LogTestResult(
            "PostgresOptions_GetConnectionString_ShouldUseDefaultValues",
            passed,
            "Default PostgresOptions (no values set)",
            "Uses default values (localhost:5432)",
            $"Length={connectionString.Length}, Host={containsDefaultHost}, Port={containsDefaultPort}"
        );

        Assert.Contains("Host=localhost", connectionString);
        Assert.Contains("Port=5432", connectionString);
    }

    [Fact]
    public void QuestDbOptions_GetPostgresConnectionString_ShouldReturnValidConnectionString()
    {
        // Arrange
        var options = new QuestDbOptions
        {
            Host = "quest-host",
            PostgresPort = 9010,
            Database = "quest-db",
            Username = "quest-user",
            Password = "quest-pass"
        };

        // Act
        var connectionString = options.GetPostgresConnectionString();

        // Assert
        var containsHost = connectionString.Contains("Host=quest-host");
        var containsPort = connectionString.Contains("Port=9010");
        var containsDatabase = connectionString.Contains("Database=quest-db");
        var containsUsername = connectionString.Contains("Username=quest-user");
        var containsPassword = connectionString.Contains("Password=quest-pass");
        
        var passed = containsHost && containsPort && containsDatabase && containsUsername && containsPassword;
        
        TestResultLogger.LogTestResult(
            "QuestDbOptions_GetPostgresConnectionString_ShouldReturnValidConnectionString",
            passed,
            $"Host={options.Host}, PostgresPort={options.PostgresPort}, Database={options.Database}",
            "Contains all expected connection string parameters",
            $"Length={connectionString.Length}, Host={containsHost}, Port={containsPort}, Database={containsDatabase}, Username={containsUsername}, Password={containsPassword}"
        );

        Assert.Contains("Host=quest-host", connectionString);
        Assert.Contains("Port=9010", connectionString);
        Assert.Contains("Database=quest-db", connectionString);
        Assert.Contains("Username=quest-user", connectionString);
        Assert.Contains("Password=quest-pass", connectionString);
    }

    [Fact]
    public void QuestDbOptions_GetPostgresConnectionString_ShouldUseDefaultValues()
    {
        // Arrange
        var options = new QuestDbOptions();

        // Act
        var connectionString = options.GetPostgresConnectionString();

        // Assert
        var containsDefaultHost = connectionString.Contains("Host=localhost");
        var containsDefaultPort = connectionString.Contains("Port=9009");
        
        var passed = containsDefaultHost && containsDefaultPort;
        
        TestResultLogger.LogTestResult(
            "QuestDbOptions_GetPostgresConnectionString_ShouldUseDefaultValues",
            passed,
            "Default QuestDbOptions (no values set)",
            "Uses default values (localhost:9009)",
            $"Length={connectionString.Length}, Host={containsDefaultHost}, Port={containsDefaultPort}"
        );

        Assert.Contains("Host=localhost", connectionString);
        Assert.Contains("Port=9009", connectionString);
    }

    [Fact]
    public void QuestDbOptions_GetInfluxConnectionString_ShouldReturnValidConnectionString()
    {
        // Arrange
        var options = new QuestDbOptions
        {
            Host = "influx-host",
            InfluxPort = 8087,
            Database = "influx-db",
            Username = "influx-user",
            Password = "influx-pass"
        };

        // Act
        var connectionString = options.GetInfluxConnectionString();

        // Assert
        var containsHost = connectionString.Contains("Host=influx-host");
        var containsPort = connectionString.Contains("Port=8087");
        var containsDatabase = connectionString.Contains("Database=influx-db");
        var containsUsername = connectionString.Contains("Username=influx-user");
        var containsPassword = connectionString.Contains("Password=influx-pass");
        
        var passed = containsHost && containsPort && containsDatabase && containsUsername && containsPassword;
        
        TestResultLogger.LogTestResult(
            "QuestDbOptions_GetInfluxConnectionString_ShouldReturnValidConnectionString",
            passed,
            $"Host={options.Host}, InfluxPort={options.InfluxPort}, Database={options.Database}",
            "Contains all expected connection string parameters",
            $"Length={connectionString.Length}, Host={containsHost}, Port={containsPort}, Database={containsDatabase}, Username={containsUsername}, Password={containsPassword}",
            passed ? null : $"Expected 'Host=influx-host' format but got '{connectionString}' (Influx URLs use different format)"
        );

        Assert.Contains("Host=influx-host", connectionString);
        Assert.Contains("Port=8087", connectionString);
        Assert.Contains("Database=influx-db", connectionString);
        Assert.Contains("Username=influx-user", connectionString);
        Assert.Contains("Password=influx-pass", connectionString);
    }

    [Fact]
    public void QuestDbOptions_GetInfluxConnectionString_ShouldUseDefaultValues()
    {
        // Arrange
        var options = new QuestDbOptions();

        // Act
        var connectionString = options.GetInfluxConnectionString();

        // Assert
        var containsDefaultHost = connectionString.Contains("Host=localhost");
        var containsDefaultPort = connectionString.Contains("Port=8086");
        
        var passed = containsDefaultHost && containsDefaultPort;
        
        TestResultLogger.LogTestResult(
            "QuestDbOptions_GetInfluxConnectionString_ShouldUseDefaultValues",
            passed,
            "Default QuestDbOptions (no values set)",
            "Uses default values (localhost:8086)",
            $"Length={connectionString.Length}, Host={containsDefaultHost}, Port={containsDefaultPort}",
            passed ? null : $"Expected 'Host=localhost' format but got '{connectionString}' (Influx URLs use different format)"
        );

        Assert.Contains("Host=localhost", connectionString);
        Assert.Contains("Port=8086", connectionString);
    }

    [Fact]
    public void QuestDbOptions_GetHttpConnectionString_ShouldReturnValidConnectionString()
    {
        // Arrange
        var options = new QuestDbOptions
        {
            Host = "http-host",
            HttpPort = 9001,
            Database = "http-db",
            Username = "http-user",
            Password = "http-pass"
        };

        // Act
        var connectionString = options.GetHttpConnectionString();

        // Assert
        var containsHost = connectionString.Contains("Host=http-host");
        var containsPort = connectionString.Contains("Port=9001");
        var containsDatabase = connectionString.Contains("Database=http-db");
        var containsUsername = connectionString.Contains("Username=http-user");
        var containsPassword = connectionString.Contains("Password=http-pass");
        
        var passed = containsHost && containsPort && containsDatabase && containsUsername && containsPassword;
        
        TestResultLogger.LogTestResult(
            "QuestDbOptions_GetHttpConnectionString_ShouldReturnValidConnectionString",
            passed,
            $"Host={options.Host}, HttpPort={options.HttpPort}, Database={options.Database}",
            "Contains all expected connection string parameters",
            $"Length={connectionString.Length}, Host={containsHost}, Port={containsPort}, Database={containsDatabase}, Username={containsUsername}, Password={containsPassword}",
            passed ? null : $"Expected 'Host=http-host' format but got '{connectionString}' (HTTP URLs use different format)"
        );

        Assert.Contains("Host=http-host", connectionString);
        Assert.Contains("Port=9001", connectionString);
        Assert.Contains("Database=http-db", connectionString);
        Assert.Contains("Username=http-user", connectionString);
        Assert.Contains("Password=http-pass", connectionString);
    }

    [Fact]
    public void QuestDbOptions_GetHttpConnectionString_ShouldUseDefaultValues()
    {
        // Arrange
        var options = new QuestDbOptions();

        // Act
        var connectionString = options.GetHttpConnectionString();

        // Assert
        var containsDefaultHost = connectionString.Contains("Host=localhost");
        var containsDefaultPort = connectionString.Contains("Port=9000");
        
        var passed = containsDefaultHost && containsDefaultPort;
        
        TestResultLogger.LogTestResult(
            "QuestDbOptions_GetHttpConnectionString_ShouldUseDefaultValues",
            passed,
            "Default QuestDbOptions (no values set)",
            "Uses default values (localhost:9000)",
            $"Length={connectionString.Length}, Host={containsDefaultHost}, Port={containsDefaultPort}",
            passed ? null : $"Expected 'Host=localhost' format but got '{connectionString}' (HTTP URLs use different format)"
        );

        Assert.Contains("Host=localhost", connectionString);
        Assert.Contains("Port=9000", connectionString);
    }
}
