using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Entities.Range;

namespace PacketProcessing.Context;

public class AppDbContext : DbContext
{
    private readonly ILogger<AppDbContext> _logger;
    
    public AppDbContext(DbContextOptions<AppDbContext> options, ILogger<AppDbContext> logger)
        : base(options)
    {
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }
    
    // Range entities
    public DbSet<TargetEntity> Targets { get; set; }
    public DbSet<RangeEntity> Ranges { get; set; }
    public DbSet<HitEntity> Hits { get; set; }
    public DbSet<EventEntity> Events { get; set; }
    
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);
        
        // Configure Range entities
        modelBuilder.Entity<TargetEntity>(entity =>
        {
            entity.ToTable("targets");
            entity.HasKey(x => x.Id);
            entity.HasIndex(x => x.Timestamp)
                .HasDatabaseName("ix_targets_timestamp");
            entity.HasMany(x => x.Hits)
                .WithOne(x => x.Target)
                .HasForeignKey(x => x.TargetId);
        });
        
        modelBuilder.Entity<RangeEntity>(entity =>
        {
            entity.ToTable("ranges");
            entity.HasKey(x => x.Id);
            entity.HasIndex(x => x.Timestamp)
                .HasDatabaseName("ix_ranges_timestamp");
            entity.HasIndex(x => x.EventId)
                .HasDatabaseName("ix_ranges_event_id");
            entity.HasOne(x => x.Event)
                .WithOne(x => x.Range)
                .HasForeignKey(x => x.EventId);
        });
        
        modelBuilder.Entity<HitEntity>(entity =>
        {
            entity.ToTable("hits");
            entity.HasKey(x => x.Id);
            entity.HasIndex(x => x.Timestamp)
                .HasDatabaseName("ix_hits_timestamp");
            entity.HasIndex(x => x.TargetId)
                .HasDatabaseName("ix_hits_target_id");
            entity.HasIndex(x => x.EventId)
                .HasDatabaseName("ix_hits_event_id");
        });
        
        modelBuilder.Entity<EventEntity>(entity =>
        {
            entity.ToTable("events");
            entity.HasKey(x => x.Id);
            entity.HasIndex(x => x.Timestamp)
                .HasDatabaseName("ix_events_timestamp");
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
            _logger.LogInformation("Checking if PostgreSQL database exists...");
            
            var databaseCreated = await Database.EnsureCreatedAsync();
            
            if (databaseCreated)
            {
                _logger.LogInformation("PostgreSQL database created successfully with all tables");
            }
            else
            {
                _logger.LogInformation("PostgreSQL database already exists, checking for missing tables...");
                
                // Check if all tables exist
                var tables = new[]
                {
                    "targets",
                    "ranges",
                    "hits",
                    "events"
                };
                
                foreach (var tableName in tables)
                {
                    var tableExists = await Database.CanConnectAsync() && 
                                    await Database.SqlQuery<int>($"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{tableName}'").FirstOrDefaultAsync() > 0;
                    
                    if (!tableExists)
                    {
                        _logger.LogWarning("Table {TableName} does not exist in PostgreSQL, creating it...", tableName);
                        await Database.ExecuteSqlAsync($"CREATE TABLE {tableName} (LIKE {tableName}_template INCLUDING ALL)");
                        _logger.LogInformation("Table {TableName} created successfully in PostgreSQL", tableName);
                    }
                    else
                    {
                        _logger.LogDebug("Table {TableName} already exists in PostgreSQL", tableName);
                    }
                }
            }
            
            return databaseCreated;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "An error occurred while ensuring PostgreSQL database exists");
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
            _logger.LogError(ex, "An error occurred while saving changes to the PostgreSQL database.");
            throw;
        }
    }
}