using Microsoft.AspNetCore.Builder;
using Serilog;

namespace PacketProcessing.Config;

public class LoggingConfiguration
{
    public static void ConfigureLogging(WebApplicationBuilder builder)
    {
        Log.Logger = new LoggerConfiguration()
            .MinimumLevel.Information()
            .WriteTo.Console()
            .WriteTo.File(
                $"logs/packet-processing-{DateTime.UtcNow:yyyy-MM-dd}.txt",
                rollingInterval: RollingInterval.Infinite,
                retainedFileCountLimit: 14,
                outputTemplate: "[{Timestamp:yyyy-MM-dd HH:mm:ss}] [{Level}]: {Message}{NewLine}"
            )
            .Enrich.WithProperty("Application", "PacketProcessing")
            .Enrich.WithProperty("Environment", builder.Environment.EnvironmentName)
            .Enrich.FromLogContext()
            .CreateLogger();
    }
}