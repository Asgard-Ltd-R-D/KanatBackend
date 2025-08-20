namespace PacketProcessing.Context;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> o) : base(o) { }

    protected override void OnModelCreating(ModelBuilder b)
    {
        
    }
}