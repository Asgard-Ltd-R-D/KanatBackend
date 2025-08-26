
using Microsoft.AspNetCore.Builder;
using PacketProcessing.Config;

var builder = WebApplication.CreateBuilder(args);

/// <summary>
/// Configure all application services and dependencies
/// </summary>
ConfigurationInjection.InjectConfigurations(builder);

var app = builder.Build();

/// <summary>
/// Ensure database is up to date with latest migrations
/// </summary>
await DatabaseMigrationHelper.EnsureDatabasesUpToDateAsync(app);

/// <summary>
/// Configure all middleware components
/// </summary>
ConfigurationInjection.InjectMiddleware(app);

/// <summary>
/// Start the web application
/// </summary>
app.Run();