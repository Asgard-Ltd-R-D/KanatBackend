using Microsoft.Extensions.Logging;
using PacketProcessing.Context;
using PacketProcessing.Entities;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Repositories.EfRepository;

public sealed class EfRepository<T> : IEfRepository<T> where T : BasePacketEntity
{
    private readonly AppDbContext _context;
    private readonly ILogger<EfRepository<T>> _logger;
    
    public EfRepository(AppDbContext qdb, ILogger<EfRepository<T>> logger)
    {
        _context = qdb ?? throw new ArgumentNullException(nameof(qdb));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }
    
    public async Task<IEnumerable<T>> GetAllPacketsAsync()
    {
        return null;
    }
    
    public async Task DeleteAllPacketsAsync()
    {
        
    }

    public async Task<IEnumerable<T>> GetPaginatedPacketsBetweenTimestampsAsync(
        DateTime startTimestamp,
        DateTime endTimestamp,
        OrderBy orderBy = OrderBy.Asc,
        int page = 1,
        int pageSize = 1_000)
    {
        return null;
    }
}