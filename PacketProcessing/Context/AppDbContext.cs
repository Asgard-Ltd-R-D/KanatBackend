using Microsoft.EntityFrameworkCore;

namespace PacketProcessing.Context;

public class AppDbContext(DbContextOptions<AppDbContext> o) : DbContext(o)
{
    protected override void OnModelCreating(ModelBuilder b)
    {
        
    }
}