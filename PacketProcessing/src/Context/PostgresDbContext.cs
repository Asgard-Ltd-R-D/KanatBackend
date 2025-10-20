using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Entities.Range;

namespace PacketProcessing.Context;

public sealed class PostgresDbContext : DbContext
{
    private readonly ILogger<PostgresDbContext> _logger;
    
    public PostgresDbContext(DbContextOptions<PostgresDbContext> options, ILogger<PostgresDbContext> logger)
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
        modelBuilder.Entity<RangeEntity>(entity =>
        {
            entity.ToTable("ranges");
            entity.HasKey(x => x.Id);
            
            // Configure columns
            entity.Property(x => x.Id).HasColumnName("id");
            entity.Property(x => x.Timestamp).HasColumnName("timestamp");
            entity.Property(x => x.Start).HasColumnName("start_time");
            entity.Property(x => x.End).HasColumnName("end_time");
            entity.Property(x => x.Description).HasColumnName("description").HasMaxLength(500);
            
            // Configure indexes
            entity.HasIndex(x => x.Timestamp)
                .HasDatabaseName("ix_ranges_timestamp");
            entity.HasIndex(x => x.Start)
                .HasDatabaseName("ix_ranges_start_time");
            entity.HasIndex(x => x.End)
                .HasDatabaseName("ix_ranges_end_time");
            
            // Configure navigation properties
            entity.HasMany(x => x.Events)
                .WithOne(x => x.Range)
                .HasForeignKey(x => x.RangeId)
                .OnDelete(DeleteBehavior.Cascade);
        });
        
        modelBuilder.Entity<EventEntity>(entity =>
        {
            entity.ToTable("events");
            entity.HasKey(x => x.Id);
            
            // Configure columns
            entity.Property(x => x.Id).HasColumnName("id");
            entity.Property(x => x.Timestamp).HasColumnName("timestamp");
            entity.Property(x => x.Start).HasColumnName("start_time");
            entity.Property(x => x.End).HasColumnName("end_time");
            entity.Property(x => x.RangeId).HasColumnName("range_id");
            
            // Configure indexes
            entity.HasIndex(x => x.Timestamp)
                .HasDatabaseName("ix_events_timestamp");
            entity.HasIndex(x => x.Start)
                .HasDatabaseName("ix_events_start_time");
            entity.HasIndex(x => x.End)
                .HasDatabaseName("ix_events_end_time");
            entity.HasIndex(x => x.RangeId)
                .HasDatabaseName("ix_events_range_id");
            
            // Configure foreign key constraint
            entity.HasOne(x => x.Range)
                .WithMany(x => x.Events)
                .HasForeignKey(x => x.RangeId)
                .OnDelete(DeleteBehavior.Cascade);
            
            // Configure navigation properties
            entity.HasMany(x => x.Hits)
                .WithOne(x => x.Event)
                .HasForeignKey(x => x.EventId)
                .OnDelete(DeleteBehavior.Cascade);
        });
        
        modelBuilder.Entity<TargetEntity>(entity =>
        {
            entity.ToTable("targets");
            entity.HasKey(x => x.Id);
            
            // Configure columns
            entity.Property(x => x.Id).HasColumnName("id");
            entity.Property(x => x.Timestamp).HasColumnName("timestamp");
            entity.Property(x => x.PosX).HasColumnName("pos_x");
            entity.Property(x => x.PosY).HasColumnName("pos_y");
            entity.Property(x => x.CenterX).HasColumnName("center_x");
            entity.Property(x => x.CenterY).HasColumnName("center_y");
            
            // Configure indexes
            entity.HasIndex(x => x.Timestamp)
                .HasDatabaseName("ix_targets_timestamp");
            entity.HasIndex(x => x.PosX)
                .HasDatabaseName("ix_targets_pos_x");
            entity.HasIndex(x => x.PosY)
                .HasDatabaseName("ix_targets_pos_y");
            
            // Configure navigation properties
            entity.HasMany(x => x.Hits)
                .WithOne(x => x.Target)
                .HasForeignKey(x => x.TargetId)
                .OnDelete(DeleteBehavior.Cascade);
        });
        
        modelBuilder.Entity<HitEntity>(entity =>
        {
            entity.ToTable("hits");
            entity.HasKey(x => x.Id);
            
            // Configure columns
            entity.Property(x => x.Id).HasColumnName("id");
            entity.Property(x => x.Timestamp).HasColumnName("timestamp");
            entity.Property(x => x.RangeToTarget).HasColumnName("range_to_target");
            entity.Property(x => x.PosX).HasColumnName("pos_x");
            entity.Property(x => x.PosY).HasColumnName("pos_y");
            entity.Property(x => x.CenterX).HasColumnName("center_x");
            entity.Property(x => x.CenterY).HasColumnName("center_y");
            entity.Property(x => x.TargetId).HasColumnName("target_id");
            entity.Property(x => x.EventId).HasColumnName("event_id");
            
            // Configure indexes
            entity.HasIndex(x => x.Timestamp)
                .HasDatabaseName("ix_hits_timestamp");
            entity.HasIndex(x => x.TargetId)
                .HasDatabaseName("ix_hits_target_id");
            entity.HasIndex(x => x.EventId)
                .HasDatabaseName("ix_hits_event_id");
            entity.HasIndex(x => x.RangeToTarget)
                .HasDatabaseName("ix_hits_range_to_target");
            
            // Configure foreign key constraints
            entity.HasOne(x => x.Target)
                .WithMany(x => x.Hits)
                .HasForeignKey(x => x.TargetId)
                .OnDelete(DeleteBehavior.Cascade);
            
            entity.HasOne(x => x.Event)
                .WithMany(x => x.Hits)
                .HasForeignKey(x => x.EventId)
                .OnDelete(DeleteBehavior.Cascade);
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
                    // Use parameterized scalar EXISTS with alias "Value" so EF can project to a scalar type
                    var tableExists = await Database.CanConnectAsync() &&
                                       await Database.SqlQuery<bool>($"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = {tableName}) AS \"Value\"").FirstAsync();

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