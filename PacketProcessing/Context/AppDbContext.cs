using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using PacketProcessing.Config;

namespace PacketProcessing.Context;

public class AppDbContext : DbContext
{
    private readonly ILogger<AppDbContext> _logger;
    private readonly ApplicationOptions.DbOptions _dbOptions;
    private readonly List<string> _tables = [];
    
    public AppDbContext(
        DbContextOptions<AppDbContext> contextOptions,
        IOptions<ApplicationOptions.DbOptions> dbOptions,
        ApplicationOptions.SnifferOptions snifferOptions,
        ILogger<AppDbContext> logger) : base(contextOptions)
    {
        _logger = logger;
        _dbOptions = dbOptions.Value;
        snifferOptions.Pipelines.ForEach(p => _tables.Add(p.Name));
    }

    protected override void OnModelCreating(ModelBuilder b)
    {

    }

    public void EnsureDatabaseCreated()
    {
        try
        {
            if (!Database.CanConnect())
            {
                _logger.LogWarning("Database connection failed. Attempting to create the database...");
                Database.EnsureCreated();
                _logger.LogInformation("Database created successfully.");
            }
            else
            {
                _logger.LogInformation("Database connection successful.");
            }
            
            // Verify that all tables were created successfully
            VerifyTablesExist();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error ensuring database creation.");
            throw new ApplicationException("Database setup failed.", ex);
        }
    }

    private void VerifyTablesExist()
    {
        try
        {
            foreach (var table in _tables)
            {
                var tableExists = Database.ExecuteSql($"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table}'");
                if (tableExists == 0)
                {
                    _logger.LogWarning($"Table {table} does not exist, attempting to create it manually");
                    Database.EnsureCreated();
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Could not verify tables exist");
        }
    }
}