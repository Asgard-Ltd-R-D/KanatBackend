using Microsoft.Extensions.Logging;
using PacketProcessing.Entities;
using PacketProcessing.Repositories.EfRepository;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Utils.Enums;
using QuestDB.Senders;

namespace PacketProcessing.Repositories;

public sealed class Repository<T> : IRepository<T> where T : BasePacketEntity
{
    private readonly IInfluxRepository<T> _influxRepo;
    private readonly IEfRepository<T> _efRepo;
    private readonly ILogger<Repository<T>> _logger;

    public Repository(
        IInfluxRepository<T> influxRepo,
        IEfRepository<T> efRepo,
        ILogger<Repository<T>> logger)
    {
        _influxRepo = influxRepo ?? throw new ArgumentNullException(nameof(influxRepo));
        _efRepo = efRepo ?? throw new ArgumentNullException(nameof(efRepo));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }
    
    public Task WriteAsync(ISender sender, T entity, CancellationToken ct = default)
        => _influxRepo.WriteAsync(sender, entity, ct);

    public Task WriteBatchAsync(ISender sender, IReadOnlyList<T> batch, CancellationToken ct = default)
        => _influxRepo.WriteBatchAsync(sender, batch, ct);

    public Task<IEnumerable<T>> GetAllPacketsAsync()
        => _efRepo.GetAllPacketsAsync();

    public Task DeleteAllPacketsAsync()
        => _efRepo.DeleteAllPacketsAsync();

    public Task<IEnumerable<T>> GetPaginatedPacketsBetweenTimestampsAsync(
        DateTime startTimestamp,
        DateTime endTimestamp,
        OrderBy orderBy = OrderBy.Asc,
        int page = 1,
        int pageSize = 1_000)
        => _efRepo.GetPaginatedPacketsBetweenTimestampsAsync(
            startTimestamp, endTimestamp, orderBy, page, pageSize);
    
    // EF Repository methods
    public Task<T> AddAsync(T entity)
        => _efRepo.AddAsync(entity);
    
    public Task<int> AddRangeAsync(IEnumerable<T> entities)
        => _efRepo.AddRangeAsync(entities);
    
    public Task<T?> GetByIdAsync(Guid id)
        => _efRepo.GetByIdAsync(id);
    
    public Task<T> UpdateAsync(T entity)
        => _efRepo.UpdateAsync(entity);
    
    public Task<bool> DeleteAsync(Guid id)
        => _efRepo.DeleteAsync(id);

    public async ValueTask DisposeAsync()
    {
        // If composed repos are async-disposable, dispose them
        if (_influxRepo is IAsyncDisposable iad1)
            await iad1.DisposeAsync().ConfigureAwait(false);

        if (_efRepo is IAsyncDisposable iad2)
            await iad2.DisposeAsync().ConfigureAwait(false);

        GC.SuppressFinalize(this);
    }
}