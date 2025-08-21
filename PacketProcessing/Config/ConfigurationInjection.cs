namespace PacketProcessing.Config;

using Microsoft.EntityFrameworkCore;
using Serilog;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using PacketProcessing.Context;
using Microsoft.Extensions.Hosting;
using Microsoft.AspNetCore.Hosting;
using PacketProcessing.Capture;
using PacketProcessing.Entities;

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

        // Register DB Context with proper configuration for QuestDB (using PostgreSQL wire protocol)
        var connectionString = builder.Configuration.GetConnectionString("PSQL");
        // 1) Register your scoped AppDbContext, but force its Options to be singleton
        builder.Services.AddDbContext<AppDbContext>(
            // configuration callback
            (sp, opts) => opts
                .UseNpgsql(connectionString)
                .EnableSensitiveDataLogging(builder.Environment.IsDevelopment())
                .EnableDetailedErrors(builder.Environment.IsDevelopment())
                .ConfigureWarnings(w => 
                    w.Ignore(CoreEventId.NavigationBaseIncludeIgnored)),
            // The DbContext itself remains scoped
            contextLifetime: ServiceLifetime.Scoped,
            // The Options object becomes singleton
            optionsLifetime: ServiceLifetime.Singleton
        );

        // 2) Register the factory as before
        builder.Services.AddDbContextFactory<AppDbContext>(opts =>
            opts.UseNpgsql(connectionString)
                .EnableSensitiveDataLogging(builder.Environment.IsDevelopment())
                .EnableDetailedErrors(builder.Environment.IsDevelopment())
                .ConfigureWarnings(w =>
                    w.Ignore(CoreEventId.NavigationBaseIncludeIgnored)));

        // Ensure DB is set up before services
        EnvironmentConfiguration.LoadConfigurations(builder);

        // Register Repositories & Services
        //TODO: Implement Repositories and Services

        
        // Register Background Services
        builder.Services.AddHostedService<BaseCaptureService<MotionPacketEntity>>();
        builder.Services.AddHostedService<BaseCaptureService<SafetyPacketEntity>>();
        builder.Services.AddHostedService<BaseCaptureService<OnVIFPacketEntity>>();
        
        // Register Services (including CORS)
        CorsConfiguration.ConfigureCorsServices(builder.Services);

        // Register Health Checks
        builder.Services.AddHealthChecks();

        // Register Swagger & API Controllers
        builder.Services.AddEndpointsApiExplorer();
        builder.Services.AddSwaggerGen();
        builder.Services.AddControllers();
        // Configure routing to use lowercase URLs
        builder.Services.AddRouting(options => options.LowercaseUrls = true);
        

        // Configure Kestrel server limits
        builder.WebHost.ConfigureKestrel(options =>
        {
            options.Limits.MaxRequestBodySize = 200 * 1024 * 1024; // 200MB
            options.Limits.KeepAliveTimeout = TimeSpan.FromMinutes(10);
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
    public static void InjectMiddleware(WebApplication app)
    {
        // Global exception handler should be first
        app.UseGlobalExceptionHandler();

        // Enable CORS Middleware
        CorsConfiguration.ConfigureCorsMiddleware(app);

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
}