namespace PacketProcessing.Config;

using Serilog;
using Serilog.Events;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.AspNetCore.Hosting;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Services.Realtime.Networking;
using System.Threading.Channels;
using Microsoft.Extensions.Logging;
using PacketProcessing.Repositories.InfluxRepository;
using Microsoft.Extensions.Options;
using PacketProcessing.Services.Realtime.Storage;
using PacketProcessing.Services.Realtime;
using PacketProcessing.Services.Transmission;
using PacketProcessing.Services.Playback;
using PacketProcessing.Services;
using PacketProcessing.Utils.Parsers;
using PacketProcessing.Repositories.EfRepository;
using System.Text.Json.Serialization;
using PacketProcessing.Utils.Enums;
using Microsoft.AspNetCore.Http;

/// <summary>
/// Configuration and Dependency Injection Manager
/// 
/// Registers all application services, middleware, and dependencies.
/// Follows layered architecture: Controllers → Services → Repositories → DbContext
/// </summary>
public class ConfigurationInjection
{
    /// <summary>
    /// Configures all application services and dependencies
    /// </summary>
    /// <param name="builder">The WebApplicationBuilder instance</param>
    public static void InjectConfigurations(WebApplicationBuilder builder)
    {
        // Configure Logging
        LoggingConfiguration.ConfigureLogging(builder);
        builder.Host.UseSerilog();

        // Configure all database services using unified DatabaseConfiguration
        DatabaseConfiguration.ConfigureServices(builder.Services, builder.Configuration);

        // Ensure DB is set up before services
        EnvironmentConfiguration.LoadConfigurations(builder);

        // Register Repositories & Services
        //TODO: Implement Repositories and Services

        var config = builder.Configuration;
        
        // === Channels ===
        builder.Services.AddSingleton(sp =>
        {
            var max = config.GetValue<int>("DataPipes:MotionCapture:Channel:Members", 1000000);
            return Channel.CreateBounded<MotionPacketEntity>(new BoundedChannelOptions(max)
            {
                FullMode = BoundedChannelFullMode.Wait,  // Block instead of drop - guarantees delivery
                SingleReader = false,
                SingleWriter = false
            });
        });

        builder.Services.AddSingleton(sp =>
        {
            var max = config.GetValue<int>("DataPipes:SafetyCapture:Channel:Members", 1000000);
            return Channel.CreateBounded<SafetyPacketEntity>(new BoundedChannelOptions(max)
            {
                FullMode = BoundedChannelFullMode.Wait,  // Block instead of drop - guarantees delivery
                SingleReader = false,
                SingleWriter = false
            });
        });

        builder.Services.AddSingleton(sp =>
        {
            var max = config.GetValue<int>("DataPipes:OnVIFCapture:Channel:Members", 100000);
            return Channel.CreateBounded<OnVIFPacketEntity>(new BoundedChannelOptions(max)
            {
                FullMode = BoundedChannelFullMode.Wait,  // Block instead of drop - guarantees delivery
                SingleReader = false,
                SingleWriter = false
            });
        });

        // === Transmission & Playback Services (register before handlers) ===
        builder.Services.AddSingleton<IInfluxRepositoryFactory, InfluxRepositoryFactory>();
        builder.Services.AddSingleton<ITransmissionService, TransmissionService>();
        builder.Services.AddSingleton<IPlaybackService, PlaybackService>();

        // === Parsers ===
        builder.Services.AddSingleton<MotionPacketParser>();
        builder.Services.AddSingleton<SafetyPacketParser>();
        builder.Services.AddSingleton<OnVifPacketParser>();
        builder.Services.AddSingleton<ParseMapper>();

        // === Handlers ===
        builder.Services.AddSingleton<HandlerService<MotionPacketEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<HandlerService<MotionPacketEntity>>>();
            var channel = sp.GetRequiredService<Channel<MotionPacketEntity>>();
            var cfg = sp.GetRequiredService<IConfiguration>();
            var transmissionService = sp.GetRequiredService<ITransmissionService>();
            var parseMapper = sp.GetRequiredService<ParseMapper>();
            var statsObserver = sp.GetRequiredService<Utils.Observers.StatsObserver>();
            
            var handler = new HandlerService<MotionPacketEntity>("DataPipes:MotionCapture", transmissionService, logger, channel, cfg, parseMapper, statsObserver);
            
            return handler;
        });
        
        // Register interface mapping for RealtimeService
        builder.Services.AddSingleton<IHandlerService<MotionPacketEntity>>(sp => 
            sp.GetRequiredService<HandlerService<MotionPacketEntity>>());

        builder.Services.AddSingleton<HandlerService<SafetyPacketEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<HandlerService<SafetyPacketEntity>>>();
            var channel = sp.GetRequiredService<Channel<SafetyPacketEntity>>();
            var cfg = sp.GetRequiredService<IConfiguration>();
            var transmissionService = sp.GetRequiredService<ITransmissionService>();
            var parseMapper = sp.GetRequiredService<ParseMapper>();
            var statsObserver = sp.GetRequiredService<Utils.Observers.StatsObserver>();
            var handler = new HandlerService<SafetyPacketEntity>("DataPipes:SafetyCapture", transmissionService, logger, channel, cfg, parseMapper, statsObserver);
            
            return handler;
        });
        
        // Register interface mapping for RealtimeService
        builder.Services.AddSingleton<IHandlerService<SafetyPacketEntity>>(sp => 
            sp.GetRequiredService<HandlerService<SafetyPacketEntity>>());

        builder.Services.AddSingleton<HandlerService<OnVIFPacketEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<HandlerService<OnVIFPacketEntity>>>();
            var channel = sp.GetRequiredService<Channel<OnVIFPacketEntity>>();
            var cfg = sp.GetRequiredService<IConfiguration>();
            var transmissionService = sp.GetRequiredService<ITransmissionService>();
            var parseMapper = sp.GetRequiredService<ParseMapper>();
            var statsObserver = sp.GetRequiredService<Utils.Observers.StatsObserver>();
            
            var handler = new HandlerService<OnVIFPacketEntity>("DataPipes:OnVIFCapture", transmissionService, logger, channel, cfg, parseMapper, statsObserver);
            return handler;
        });
        
        // Register interface mapping for RealtimeService
        builder.Services.AddSingleton<IHandlerService<OnVIFPacketEntity>>(sp => 
            sp.GetRequiredService<HandlerService<OnVIFPacketEntity>>());

        // === Configuration ===
        builder.Services.Configure<QuestDbConfiguration>(config.GetSection("Database"));

        // === Writers ===
        // Register each writer as singleton, then expose as both IDbWriterService and IHostedService
        builder.Services.AddSingleton<DbWriterService<MotionPacketEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<DbWriterService<MotionPacketEntity>>>();
            var channel = sp.GetRequiredService<Channel<MotionPacketEntity>>();
            var repository = sp.GetRequiredService<IInfluxRepository<MotionPacketEntity>>();
            var options = sp.GetRequiredService<IOptions<QuestDbConfiguration>>();
            var config = sp.GetRequiredService<IConfiguration>();
            var statsObserver = sp.GetRequiredService<Utils.Observers.StatsObserver>();
            return new DbWriterService<MotionPacketEntity>(logger, channel, repository, options, config, statsObserver);
        });
        builder.Services.AddSingleton<IDbWriterService<MotionPacketEntity>>(sp => 
            sp.GetRequiredService<DbWriterService<MotionPacketEntity>>());
        
        builder.Services.AddSingleton<DbWriterService<SafetyPacketEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<DbWriterService<SafetyPacketEntity>>>();
            var channel = sp.GetRequiredService<Channel<SafetyPacketEntity>>();
            var repository = sp.GetRequiredService<IInfluxRepository<SafetyPacketEntity>>();
            var options = sp.GetRequiredService<IOptions<QuestDbConfiguration>>();
            var config = sp.GetRequiredService<IConfiguration>();
            var statsObserver = sp.GetRequiredService<Utils.Observers.StatsObserver>();
            return new DbWriterService<SafetyPacketEntity>(logger, channel, repository, options, config, statsObserver);
        });
        builder.Services.AddSingleton<IDbWriterService<SafetyPacketEntity>>(sp => 
            sp.GetRequiredService<DbWriterService<SafetyPacketEntity>>());
        
        builder.Services.AddSingleton<DbWriterService<OnVIFPacketEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<DbWriterService<OnVIFPacketEntity>>>();
            var channel = sp.GetRequiredService<Channel<OnVIFPacketEntity>>();
            var repository = sp.GetRequiredService<IInfluxRepository<OnVIFPacketEntity>>();
            var options = sp.GetRequiredService<IOptions<QuestDbConfiguration>>();
            var config = sp.GetRequiredService<IConfiguration>();
            var statsObserver = sp.GetRequiredService<Utils.Observers.StatsObserver>();
            return new DbWriterService<OnVIFPacketEntity>(logger, channel, repository, options, config, statsObserver);
        });
        builder.Services.AddSingleton<IDbWriterService<OnVIFPacketEntity>>(sp => 
            sp.GetRequiredService<DbWriterService<OnVIFPacketEntity>>());

        // === Register Writers and Handlers as hosted background services ===
        builder.Services.AddSingleton<IHostedService>(sp => sp.GetRequiredService<DbWriterService<MotionPacketEntity>>());
        builder.Services.AddSingleton<IHostedService>(sp => sp.GetRequiredService<DbWriterService<SafetyPacketEntity>>());
        builder.Services.AddSingleton<IHostedService>(sp => sp.GetRequiredService<DbWriterService<OnVIFPacketEntity>>());
        
        builder.Services.AddSingleton<IHostedService>(sp => sp.GetRequiredService<HandlerService<MotionPacketEntity>>());
        builder.Services.AddSingleton<IHostedService>(sp => sp.GetRequiredService<HandlerService<SafetyPacketEntity>>());
        builder.Services.AddSingleton<IHostedService>(sp => sp.GetRequiredService<HandlerService<OnVIFPacketEntity>>());

        // === Realtime Service ===
        builder.Services.AddSingleton<IRealtimeService, RealtimeService>();

        // === Repository Factories ===
        builder.Services.AddScoped(typeof(IEfRepository<>), typeof(EfRepository<>));
        builder.Services.AddScoped<IEfRepositoryFactory, EfRepositoryFactory>();

        // === Range Service ===
        builder.Services.AddScoped<IRangeService, RangeService>();

        // Device service
        builder.Services.AddSingleton<IDeviceService, DeviceService>();

        // Register Services (including CORS)
        CorsConfiguration.ConfigureCorsServices(builder.Services);

        // Register Health Checks
        builder.Services.AddHealthChecks();

        // Register Swagger & API Controllers
        builder.Services.AddEndpointsApiExplorer();
        _ = builder.Services.AddSwaggerGen(options =>
        {
            options.SwaggerDoc("v1", new Microsoft.OpenApi.Models.OpenApiInfo
            {
                Title = "Kanat Packet Processing API",
                Version = "v1",
                Description = "API for real-time packet capture and playback analysis"
            });

            // Include XML comments if available
            var xmlFile = $"{System.Reflection.Assembly.GetExecutingAssembly().GetName().Name}.xml";
            var xmlPath = Path.Combine(AppContext.BaseDirectory, xmlFile);
            if (File.Exists(xmlPath))
            {
                options.IncludeXmlComments(xmlPath);
            }

            // Define Swagger tags
            options.TagActionsBy(api =>
            {
                var controllerName = api.ActionDescriptor.RouteValues["controller"];
                var actionName = api.ActionDescriptor.RouteValues["action"];
                var routeTemplate = api.ActionDescriptor.AttributeRouteInfo?.Template;
                
                // Check if this is a dev-only endpoint
                if (api.ActionDescriptor.EndpointMetadata.Any(m => m is DevelopmentOnlyAttribute))
                {
                    return ["Development"];
                }
                
                // Group by functionality for Range controller
                if (controllerName == "Range")
                {
                    return routeTemplate switch
                    {
                        // Range Mode: mode operations
                        var route when route != null && route.Contains("mode") => ["Range Management"],
                        
                        // Range Status: devices, status, reset
                        var route when route != null && (route.Contains("devices") || route.Contains("status") || route.Contains("reset")) => ["Range Status"],
                        
                        // Range Repository: range/ranges operations
                        var route when route != null && (route.Contains("ranges") || route.Contains("range")) => ["Range Repository"],
                        
                        // Packet Repository: packet operations
                        var route when route != null && route.Contains("packets") => ["Packet Repository"],
                        
                        // Realtime operations: start/stop
                        var route when route != null && (route.Contains("realtime/start") || route.Contains("realtime/stop")) => ["Range Management"],
                        
                        // Playback operations
                        var route when route != null && route.Contains("playback") => ["Range Management"],
                        
                        _ => ["Range Management"]
                    };
                }
                
                return [controllerName ?? "Unknown"];
            });

            // Add tag descriptions
            options.DocInclusionPredicate((name, api) => true);
            
            // Configure SignalR Swagger Generation
            options.AddSignalRSwaggerGen();
        });
        builder.Services.AddControllers().AddJsonOptions(options => {
            options.JsonSerializerOptions.Converters.Add(new JsonStringEnumConverter<DataPipes>());
        });
        builder.Services.AddRouting(options => options.LowercaseUrls = true);

        
        // Register SignalR for real-time data transmission
        builder.Services.AddSignalR(options => {
            options.EnableDetailedErrors = true;
            options.ClientTimeoutInterval = TimeSpan.FromSeconds(30);
            options.KeepAliveInterval = TimeSpan.FromSeconds(15);
        }).AddJsonProtocol(options => {
            options.PayloadSerializerOptions.Converters.Add(new JsonStringEnumConverter<DataPipes>());
        });
        
        
        // Register ConnectionManager for SignalR
        builder.Services.AddSingleton<Hubs.ConnectionManager.IConnectionManager, Hubs.ConnectionManager.ConnectionManager>();
        
        // Register TelemetryBroadcaster first
        builder.Services.AddSingleton<Telemetry.TelemetryBroadcasterOptions>(provider =>
        {
            var configuration = provider.GetRequiredService<IConfiguration>();
            return new Telemetry.TelemetryBroadcasterOptions
            {
                Enabled = configuration.GetValue<bool>("Telemetry:Enabled", true),
                MaxPushRateHz = configuration.GetValue<double>("Telemetry:MaxPushRateHz", 10.0),
                MinIntervalMs = configuration.GetValue<int>("Telemetry:MinIntervalMs", 100)
            };
        });
        
        // Register TelemetryBroadcaster as singleton
        builder.Services.AddSingleton<Telemetry.TelemetryBroadcaster>();
        
        // Register Telemetry Service with broadcaster dependency
        builder.Services.AddSingleton<Telemetry.ITelemetryService>(provider =>
        {
            var broadcaster = provider.GetRequiredService<Telemetry.TelemetryBroadcaster>();
            return new Telemetry.TelemetryService(broadcaster);
        });
        
        // Register StatsObserver as singleton
        builder.Services.AddSingleton(provider =>
        {
            var telemetryService = provider.GetRequiredService<Telemetry.ITelemetryService>();
            return new Utils.Observers.StatsObserver(telemetryService, "PacketProcessing");
        });
        
        // Register TelemetryBroadcaster as hosted service
        builder.Services.AddHostedService<Telemetry.TelemetryBroadcaster>(provider =>
            provider.GetRequiredService<Telemetry.TelemetryBroadcaster>());
        
        // Configure routing to use lowercase URLs
        builder.Services.AddRouting(options => options.LowercaseUrls = true);
        
        // Configure Kestrel server limits
        builder.WebHost.ConfigureKestrel(options =>
        {
            options.Limits.MaxRequestBodySize = 200 * 1024 * 1024; // 200MB
            options.Limits.KeepAliveTimeout = TimeSpan.FromMinutes(5);
            options.Limits.RequestHeadersTimeout = TimeSpan.FromMinutes(5);
        });

        // Configure IIS options
        builder.Services.Configure<IISServerOptions>(options =>
        {
            options.MaxRequestBodySize = 200 * 1024 * 1024; // 200MB
        });
    }
    
    /// <summary>
    /// Configures all application middleware components
    /// </summary>
    /// <param name="app">The WebApplication instance</param>
    public static void InjectMiddlewareAsync(WebApplication app)
    {
        // Global exception handler should be first
        app.UseGlobalExceptionHandler();
        
        // Serve static files (telemetry dashboard) only at specific paths
        app.UseStaticFiles();

        // Use Middleware (e.g., Swagger, HTTPS Redirection)
        if (!app.Environment.IsProduction())
        {
            app.UseSwagger();
            Log.Information("Swagger is enabled on route {Route}", app.Configuration.GetValue<string>("Application:Url")+"/swagger");
            app.UseSwaggerUI();
        }
        // Map simple health check endpoint
        app.MapHealthChecks("/health");
        
        app.MapControllers();
    }
    
    /// <summary>
    /// Configures all application middleware components (synchronous version for backward compatibility)
    /// </summary>
    /// <param name="app">The WebApplication instance</param>
    public static void InjectMiddleware(WebApplication app)
    {
        // Global exception handler should be first
        app.UseGlobalExceptionHandler();

        CorsConfiguration.ConfigureCorsMiddleware(app);
        
        // Serve static files (telemetry dashboard) only at specific paths
        app.UseStaticFiles();
        
        // Map dashboard to specific path instead of root
        app.MapGet("", async context =>
        {
            var filePath = Path.Combine(app.Environment.WebRootPath, "index.html");
            if (File.Exists(filePath))
            {
                context.Response.ContentType = "text/html";
                await context.Response.SendFileAsync(filePath);
            }
            else
            {
                context.Response.StatusCode = 404;
                await context.Response.WriteAsync("Dashboard not found");
            }
        });

        // Use Middleware (e.g., Swagger, HTTPS Redirection)
        if (!app.Environment.IsProduction())
        {
            app.UseSwagger();
            Log.Information("Swagger is enabled on route {Route}", app.Configuration.GetValue<string>("Application:Url")+"/swagger");
            app.UseSwaggerUI();
        }
        // Map simple health check endpoint
        app.MapHealthChecks("/health");
        
        // Map SignalR hubs
        app.MapHub<Hubs.CustomHub>("/hubs/packets");
        app.MapHub<Telemetry.TelemetryHub>("/hubs/telemetry");
        
        app.MapControllers();
    }
}