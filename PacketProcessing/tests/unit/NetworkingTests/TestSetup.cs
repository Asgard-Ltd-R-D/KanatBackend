using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace PacketProcessing.Tests.Unit.NetworkingTests;

public static class TestSetup
{
    public static IConfiguration CreateTestConfiguration()
    {
        // Get the test project directory
        var testProjectDir = Directory.GetCurrentDirectory();
        
        // Look for appsettings.Test.json in the test project directory
        var configPath = Path.Combine(testProjectDir, "appsettings.Test.json");
        
        // If not found in current directory, try to find it in parent directories
        if (!File.Exists(configPath))
        {
            var currentDir = new DirectoryInfo(testProjectDir);
            while (currentDir.Parent != null && !File.Exists(Path.Combine(currentDir.FullName, "appsettings.Test.json")))
            {
                currentDir = currentDir.Parent;
            }
            
            if (currentDir.Parent != null)
            {
                configPath = Path.Combine(currentDir.FullName, "appsettings.Test.json");
            }
        }

        if (!File.Exists(configPath))
        {
            throw new FileNotFoundException($"Test configuration file not found. Searched in: {testProjectDir}");
        }

        var configDirectory = Path.GetDirectoryName(configPath);
        if (string.IsNullOrEmpty(configDirectory))
        {
            throw new InvalidOperationException($"Could not determine directory for configuration file: {configPath}");
        }

        return new ConfigurationBuilder()
            .SetBasePath(configDirectory)
            .AddJsonFile("appsettings.Test.json", optional: false)
            .AddEnvironmentVariables()
            .Build();
    }

    public static ILogger<T> CreateTestLogger<T>()
    {
        var loggerFactory = LoggerFactory.Create(builder =>
        {
            builder.AddConsole();
            builder.SetMinimumLevel(LogLevel.Debug);
        });
        
        return loggerFactory.CreateLogger<T>();
    }
}
