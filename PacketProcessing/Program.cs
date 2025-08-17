using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PacketProcessing.Services;
using PacketProcessing.Interfaces;
using PacketProcessing.Configuration;

namespace PacketProcessing;

class Program
{
    static async Task Main(string[] args)
    {
        var host = CreateHostBuilder(args).Build();
        
        Console.WriteLine("Packet Processing Service Starting...");
        Console.WriteLine("Press Ctrl+C to stop the service.");
        
        await host.RunAsync();
    }

    static IHostBuilder CreateHostBuilder(string[] args) =>
        Host.CreateDefaultBuilder(args)
            .ConfigureAppConfiguration((context, config) =>
            {
                config.SetBasePath(Directory.GetCurrentDirectory())
                      .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
                      .AddEnvironmentVariables()
                      .AddCommandLine(args);
            })
            .ConfigureServices((context, services) =>
            {
                // Configure QuestDB options
                services.Configure<QuestDbOptions>(
                    context.Configuration.GetSection(QuestDbOptions.SectionName));
                
                // Register services
                services.AddSingleton<IPacketStorage, QuestDbPacketStorage>();
                services.AddHostedService<PacketCaptureWorker>();
                
                // Configure logging
                services.AddLogging(builder =>
                {
                    builder.AddConsole();
                    builder.SetMinimumLevel(LogLevel.Debug);
                });
            })
            .ConfigureLogging((context, logging) =>
            {
                logging.ClearProviders();
                logging.AddConsole();
                logging.SetMinimumLevel(LogLevel.Debug);
            });
}
