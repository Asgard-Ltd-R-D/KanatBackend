using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using PacketProcessing.Context.Config;
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
    public DbSet<OnVIFPacketEntity> SessionPackets { get; set; }
    public DbSet<SafetyPacketEntity> LapPackets { get; set; }
    
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);
        
        modelBuilder.ApplyConfiguration(new MotionPacketConfig());
        modelBuilder.ApplyConfiguration(new OnVifPacketConfig());
        modelBuilder.ApplyConfiguration(new SafetyPacketConfig());
    }
    
    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    {
        base.OnConfiguring(optionsBuilder);
        
        optionsBuilder.LogTo(message => _logger.LogInformation(message), LogLevel.Information);
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