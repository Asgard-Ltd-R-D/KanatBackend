using Microsoft.Extensions.Configuration;
using PacketProcessing.Config;
using PacketProcessing.Context;

namespace PacketProcessing.Tests.Utils;

/// <summary>
/// Utility class for providing test configuration from appsettings.Test.json
/// </summary>
public static class TestConfigurationProvider
{
    private static IConfiguration? _configuration;
    private static readonly object _lock = new object();

    /// <summary>
    /// Gets the test configuration instance (singleton pattern)
    /// </summary>
    public static IConfiguration Configuration
    {
        get
        {
            if (_configuration == null)
            {
                lock (_lock)
                {
                    if (_configuration == null)
                    {
                        // Look for appsettings.Test.json in the main project directory
                        var projectRoot = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", "..", "..", ".."));
                        var testConfigPath = Path.Combine(projectRoot, "appsettings.Test.json");
                        
                        _configuration = new ConfigurationBuilder()
                            .SetBasePath(projectRoot)
                            .AddJsonFile("appsettings.Test.json", optional: false, reloadOnChange: true)
                            .AddEnvironmentVariables()
                            .Build();
                    }
                }
            }
            return _configuration;
        }
    }

    /// <summary>
    /// Creates a new configuration instance (for testing different scenarios)
    /// </summary>
    public static IConfiguration CreateConfiguration()
    {
        // Look for appsettings.Test.json in the main project directory
        var projectRoot = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", "..", "..", ".."));
        
        return new ConfigurationBuilder()
            .SetBasePath(projectRoot)
            .AddJsonFile("appsettings.Test.json", optional: false, reloadOnChange: true)
            .AddEnvironmentVariables()
            .Build();
    }

    /// <summary>
    /// Creates a configuration with custom settings
    /// </summary>
    public static IConfiguration CreateConfigurationWithSettings(Dictionary<string, string?> customSettings)
    {
        // Look for appsettings.Test.json in the main project directory
        var projectRoot = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", "..", "..", ".."));
        
        var builder = new ConfigurationBuilder()
            .SetBasePath(projectRoot)
            .AddJsonFile("appsettings.Test.json", optional: false, reloadOnChange: true)
            .AddEnvironmentVariables();

        if (customSettings.Any())
        {
            builder.AddInMemoryCollection(customSettings);
        }

        return builder.Build();
    }

    /// <summary>
    /// Gets PostgreSQL configuration from test settings
    /// </summary>
    public static PostgresConfiguration GetPostgresConfiguration()
    {
        return Configuration.GetSection("Postgres").Get<PostgresConfiguration>() 
               ?? throw new InvalidOperationException("PostgreSQL configuration not found in test settings");
    }

    /// <summary>
    /// Gets QuestDB configuration from test settings
    /// </summary>
    public static QuestDbConfiguration GetQuestDbConfiguration()
    {
        return Configuration.GetSection("QuestDb").Get<QuestDbConfiguration>() 
               ?? throw new InvalidOperationException("QuestDB configuration not found in test settings");
    }

    /// <summary>
    /// Resets the singleton configuration (useful for testing)
    /// </summary>
    public static void Reset()
    {
        lock (_lock)
        {
            _configuration = null;
        }
    }
}
