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
        
        // Start statistics monitoring task
        var statsTask = Task.Run(async () =>
        {
            try
            {
                while (!host.Services.GetRequiredService<IHostApplicationLifetime>().ApplicationStopping.IsCancellationRequested)
                {
                    await Task.Delay(10000); // Log stats every 10 seconds
                    
                    try
                    {
                        var packetStorage = host.Services.GetRequiredService<IPacketStorage>() as InfluxDbPacketStorage;
                        
                        if (packetStorage != null)
                        {
                            packetStorage.LogPacketStatistics();
                        }
                        
                        // Note: PacketCaptureWorker statistics are logged internally every 100 packets
                        // and we can't easily access the instance from here in a clean way
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"Error logging statistics: {ex.Message}");
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Statistics task error: {ex.Message}");
            }
        });
        
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
                // Configure QuestDB ILP options
                services.Configure<InfluxDbOptions>(
                    context.Configuration.GetSection(InfluxDbOptions.SectionName));
                
                // Register services
                services.AddSingleton<IPacketStorage, InfluxDbPacketStorage>();
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
