using System.Data;
using System.Data.Common;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using PacketProcessing.Entities;

namespace PacketProcessing.Context;

public class AppDbContext : DbContext
{
    private readonly ILogger<AppDbContext> _logger;
    
    public DbSet<MotionPacketEntity> MotionPackets => Set<MotionPacketEntity>();
    public DbSet<OnVIFPacketEntity> OnvifPackets => Set<OnVIFPacketEntity>();   
    public DbSet<SafetyPacketEntity> SafetyPackets => Set<SafetyPacketEntity>();
    
    public AppDbContext(DbContextOptions<AppDbContext> contextOptions, ILogger<AppDbContext> logger) : base(contextOptions)
    {
        _logger = logger;
    }

    protected override void OnModelCreating(ModelBuilder b)
    {
        // Motion packets
        b.Entity<MotionPacketEntity>(e =>
        {
            e.ToTable("motion_packets");

            e.HasKey(x => x.Id);

            e.Property(x => x.Id).ValueGeneratedNever();

            e.Property(x => x.OpCode)
                .HasMaxLength(128)
                .IsUnicode(false)
                .IsRequired(false);

            e.Property(x => x.OpCodeDescription)
                .HasMaxLength(512)
                .IsUnicode(true)
                .IsRequired(false);

            e.Property(x => x.Axis);

            e.Property(x => x.FloatValue);

            e.Property(x => x.Timestamp)
                .HasColumnType("bigint")
                .IsRequired();

            e.HasIndex(x => x.Timestamp).HasDatabaseName("ix_motion_timestamp");
            e.HasIndex(x => x.OpCode).HasDatabaseName("ix_motion_opcode");
        });

        // OnVIF packets
        b.Entity<OnVIFPacketEntity>(e =>
        {
            e.ToTable("onvif_packets");

            e.HasKey(x => x.Id);
            e.Property(x => x.Id).ValueGeneratedNever();

            e.Property(x => x.Description)
                .HasMaxLength(512)
                .IsUnicode(true)
                .IsRequired(false);

            e.Property(x => x.Zoom);
            e.Property(x => x.Measurement);

            e.Property(x => x.Timestamp)
                .HasColumnType("bigint")
                .IsRequired();

            e.HasIndex(x => x.Timestamp).HasDatabaseName("ix_onvif_timestamp");
        });

        // Safety packets
        b.Entity<SafetyPacketEntity>(e =>
        {
            e.ToTable("safety_packets");

            e.HasKey(x => x.Id);
            e.Property(x => x.Id).ValueGeneratedNever();

            e.Property(x => x.Type);

            e.Property(x => x.OpCode)
                .HasMaxLength(128)
                .IsUnicode(false)
                .IsRequired();

            e.Property(x => x.OpCodeDescription)
                .HasMaxLength(512)
                .IsUnicode(true)
                .IsRequired();

            e.Property(x => x.State)
                .HasMaxLength(128)
                .IsUnicode(false)
                .IsRequired();

            e.Property(x => x.Timestamp)
                .HasColumnType("bigint")
                .IsRequired();

            e.HasIndex(x => x.Timestamp).HasDatabaseName("ix_safety_timestamp");
            e.HasIndex(x => x.OpCode).HasDatabaseName("ix_safety_opcode");
        });
    }

    /// <summary>
    /// Create/upgrade the database and required tables.
    /// Prefer Migrate(); optionally fall back to EnsureCreated() in dev only.
    /// </summary>
    public void EnsureDatabaseCreated()
    {
        try
        {
            _logger.LogInformation("Checking database connectivity...");
            if (!Database.CanConnect())
            {
                _logger.LogWarning("Database not reachable yet.");
            }

            _logger.LogInformation("Applying EF Core migrations (if any)...");
            Database.Migrate();
            _logger.LogInformation("Migrations applied successfully.");

            VerifyModelTablesExist();
        }
        catch (Exception migrateEx)
        {
            _logger.LogError(migrateEx, "Database.Migrate() failed.");

            try
            {
                _logger.LogWarning("Falling back to Database.EnsureCreated() (DEV only)...");
                _logger.LogInformation(Database.EnsureCreated()
                    ? "Database and tables created via EnsureCreated()."
                    : "EnsureCreated() found database already created.");
                
                VerifyModelTablesExist();
            }
            catch (Exception ecEx)
            {
                _logger.LogError(ecEx, "EnsureCreated() also failed.");
                throw;
            }
            
            throw;
        }
    }

    /// <summary>
    /// Logs a warning if an entity’s mapped table is missing.
    /// With migrations, the next Migrate() run will create it.
    /// </summary>
    private void VerifyModelTablesExist()
    {
        try
        {
            var conn = Database.GetDbConnection();
            var provider = Database.ProviderName ?? string.Empty;

            _logger.LogInformation("Verifying mapped tables exist (provider: {Provider})...", provider);

            if (conn.State != ConnectionState.Open)
                conn.Open();

            foreach (var entityType in Model.GetEntityTypes())
            {
                var schema = entityType.GetSchema() ?? GetDefaultSchema(provider);
                var table = entityType.GetTableName();
                if (string.IsNullOrWhiteSpace(table)) continue;

                var exists = TableExists(conn, provider, schema, table);
                if (!exists)
                {
                    _logger.LogWarning("Table missing: {Schema}.{Table}. Add a migration and call Migrate() to create it.",
                        schema, table);
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Could not verify tables exist");
        }
    }
    
    private static string? GetDefaultSchema(string provider)
    {
        // SQL Server default schema is dbo; PostgreSQL default is public;
        if (provider.Contains("SqlServer", StringComparison.OrdinalIgnoreCase)) return "dbo";
        return provider.Contains("Npgsql", StringComparison.OrdinalIgnoreCase) ? "public" : null;
    }
    
    private static bool TableExists(DbConnection conn, string provider, string? schema, string table)
    {
        using var cmd = conn.CreateCommand();

        if (provider.Contains("SqlServer", StringComparison.OrdinalIgnoreCase))
        {
            cmd.CommandText = schema is null
                ? @"SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = @p0"
                : @"SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = @p0 AND TABLE_NAME = @p1";
            if (schema is null)
            {
                var p0 = cmd.CreateParameter(); p0.ParameterName = "@p0"; p0.Value = table; cmd.Parameters.Add(p0);
            }
            else
            {
                var p0 = cmd.CreateParameter(); p0.ParameterName = "@p0"; p0.Value = schema; cmd.Parameters.Add(p0);
                var p1 = cmd.CreateParameter(); p1.ParameterName = "@p1"; p1.Value = table; cmd.Parameters.Add(p1);
            }
        }
        
        else if (provider.Contains("Npgsql", StringComparison.OrdinalIgnoreCase))
        {
            cmd.CommandText = schema is null
                ? @"SELECT 1 FROM information_schema.tables WHERE table_name = @p0"
                : @"SELECT 1 FROM information_schema.tables WHERE table_schema = @p0 AND table_name = @p1";
            if (schema is null)
            {
                var p0 = cmd.CreateParameter(); p0.ParameterName = "@p0"; p0.Value = table; cmd.Parameters.Add(p0);
            }
            else
            {
                var p0 = cmd.CreateParameter(); p0.ParameterName = "@p0"; p0.Value = schema; cmd.Parameters.Add(p0);
                var p1 = cmd.CreateParameter(); p1.ParameterName = "@p1"; p1.Value = table; cmd.Parameters.Add(p1);
            }
        }
        
        else
        {
            return false;
        }

        var result = cmd.ExecuteScalar();
        return result != null && result != DBNull.Value;
    }
}