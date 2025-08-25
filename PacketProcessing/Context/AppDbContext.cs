using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using PacketProcessing.Entities;

namespace PacketProcessing.Context;

public class AppDbContext : DbContext
{
    private readonly ILogger<AppDbContext> _logger;
    
    public AppDbContext(DbContextOptions<AppDbContext> options, ILogger<AppDbContext> logger)
        : base(options)
    {
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }
    
    public DbSet<MotionPacketEntity> MotionPackets { get; set; }
    public DbSet<OnVIFPacketEntity> OnVifPackets { get; set; }
    public DbSet<SafetyPacketEntity> SafetyPackets { get; set; }
    
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);
        
        // Configure entities using data annotations instead of separate config classes
        modelBuilder.Entity<MotionPacketEntity>(entity =>
        {
            entity.ToTable("motion_packets");
            entity.HasKey(x => x.Id);
            entity.HasIndex(x => new { x.Id, x.Timestamp })
                .HasDatabaseName("ix_motion_packets_sensor_ts");
        });
        
        modelBuilder.Entity<OnVIFPacketEntity>(entity =>
        {
            entity.ToTable("onvif_packets");
            entity.HasKey(x => x.Id);
            entity.HasIndex(x => new { x.Id, x.Timestamp })
                .HasDatabaseName("ix_onvif_packets_sensor_ts");
        });
        
        modelBuilder.Entity<SafetyPacketEntity>(entity =>
        {
            entity.ToTable("safety_packets");
            entity.HasKey(x => x.Id);
            entity.HasIndex(x => new { x.Id, x.Timestamp })
                .HasDatabaseName("ix_safety_packets_sensor_ts");
        });
    }
    
    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    {
        base.OnConfiguring(optionsBuilder);
        
        optionsBuilder.LogTo(message => _logger.LogInformation(message), LogLevel.Information);
    }
    
    /// <summary>
    /// Ensures the database exists and all tables are created according to the entities
    /// </summary>
    /// <returns>True if database was created, false if it already existed</returns>
    public async Task<bool> EnsureDatabaseAsync()
    {
        try
        {
            _logger.LogInformation("Checking if database exists...");
            
            var databaseCreated = await Database.EnsureCreatedAsync();
            
            if (databaseCreated)
            {
                _logger.LogInformation("Database created successfully with all tables");
            }
            else
            {
                _logger.LogInformation("Database already exists, checking for missing tables...");
                
                // Check if all tables exist
                var tables = new[]
                {
                    "motion_packets",
                    "onvif_packets", 
                    "safety_packets"
                };
                
                foreach (var tableName in tables)
                {
                    var tableExists = await Database.CanConnectAsync() && 
                                    await Database.SqlQueryRaw<int>($"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{tableName}'").FirstOrDefaultAsync() > 0;
                    
                    if (!tableExists)
                    {
                        _logger.LogWarning("Table {TableName} does not exist, creating it...", tableName);
                        await Database.ExecuteSqlRawAsync($"CREATE TABLE {tableName} (LIKE {tableName}_template INCLUDING ALL)");
                        _logger.LogInformation("Table {TableName} created successfully", tableName);
                    }
                    else
                    {
                        _logger.LogDebug("Table {TableName} already exists", tableName);
                    }
                }
            }
            
            return databaseCreated;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "An error occurred while ensuring database exists");
            throw;
        }
    }
    
    public override async Task<int> SaveChangesAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            return await base.SaveChangesAsync(cancellationToken);
        }
        catch (DbUpdateException ex)
        {
            _logger.LogError(ex, "An error occurred while saving changes to the database.");
            throw;
        }
    }
}