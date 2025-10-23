using Microsoft.AspNetCore.Builder;
using Serilog;
using Serilog.Events;

namespace PacketProcessing.Config;

public class LoggingConfiguration
{
    public static void ConfigureLogging(WebApplicationBuilder builder)
    {
        Log.Logger = new LoggerConfiguration()
            .ReadFrom.Configuration(builder.Configuration)
            .MinimumLevel.Debug()
            .MinimumLevel.Override("Microsoft", LogEventLevel.Information)
            .MinimumLevel.Override("Microsoft.Hosting.Lifetime", LogEventLevel.Information)
            .MinimumLevel.Override("System", LogEventLevel.Warning)
            .Filter.ByExcluding(logEvent => 
                logEvent.Properties.ContainsKey("RequestPath") && 
                logEvent.Properties["RequestPath"].ToString().Contains("/health"))
            .WriteTo.Console(
                outputTemplate: "[{Timestamp:yyyy-MM-dd HH:mm:ss}] [{Level:u3}]: {Message:lj}{NewLine}{Exception}"
            )
            .WriteTo.File(
                $"logs/packet-processing-{DateTime.UtcNow:yyyy-MM-dd}.txt",
                rollingInterval: RollingInterval.Infinite,
                retainedFileCountLimit: 14,
                outputTemplate: "[{Timestamp:yyyy-MM-dd HH:mm:ss}] [{Level:u3}]: {Message:lj}{NewLine}{Exception}",
                restrictedToMinimumLevel: LogEventLevel.Debug
            )
            .Enrich.WithProperty("Application", "PacketProcessing")
            .Enrich.WithProperty("Environment", builder.Environment.EnvironmentName)
            .Enrich.FromLogContext()
            .CreateLogger();
    }
}