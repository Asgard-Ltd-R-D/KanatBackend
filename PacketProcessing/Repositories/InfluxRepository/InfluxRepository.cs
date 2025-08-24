using Microsoft.Extensions.Logging;
using PacketProcessing.Entities;
using PacketProcessing.Utils.QuestDB;
using QuestDB.Senders;

namespace PacketProcessing.Repositories.InfluxRepository;

public class InfluxRepository<T> : IInfluxRepository<T>, IAsyncDisposable where T : BasePacketEntity
{
    private ILogger<InfluxRepository<T>> _logger;

    public InfluxRepository(ILogger<InfluxRepository<T>> logger) => _logger = logger;

    public async Task WriteAsync(ISender sender, T entity, CancellationToken ct = default)
    {
        // if entity or sender is null, throw ArgumentNullException
        ArgumentNullException.ThrowIfNull(entity);
        ArgumentNullException.ThrowIfNull(sender);
        
        try
        {
            // map entity to RawRow using PacketRowMapper
            var row = PacketRowMapper<T>.Map(entity);

            // create a new RawTable with the same structure as row, and use it to create a transaction
            var table = row.Table;
            sender.Transaction(table);

            // apply the row to the sender
            row.Apply(sender);

            // commit the transaction
            await sender.CommitAsync(ct).ConfigureAwait(false);
            _logger.LogInformation("Sent packet to DB: {Id}", entity.Id);
        } catch (Exception ex)
        {
            _logger.LogError(ex, ex.Message);
            try { sender.Rollback(); } catch { /* best effort */ }
            throw;
        }
    }

    public async Task WriteBatchAsync(ISender sender, IReadOnlyList<T> batch, CancellationToken ct = default)
    {
        // if entity or sender is null, throw ArgumentNullException
        ArgumentNullException.ThrowIfNull(sender);
        if (batch.Count == 0) return;
        ct.ThrowIfCancellationRequested();
        
        // sort batch by Timestamp
        var rows = batch
            .Select(PacketRowMapper<T>.Map)
            .OrderBy(r => r.TimestampUtc)
            .ToList();

        try
        {
            // create a new RawTable with the same structure as the first row, and use it to create a transaction
            var table = rows[0].Table;
            sender.Transaction(table);

            foreach (var row in rows)
            {
                ct.ThrowIfCancellationRequested();
                row.Apply(sender); // append, no commit
            }

            await sender.CommitAsync(ct).ConfigureAwait(false);
            _logger.LogInformation("Sent batch of {Count} rows to {Table}", rows.Count, table);
        } catch (Exception ex)
        {
            _logger.LogError(ex, "Failed writing batch for {Type}", typeof(T).Name);
            try { sender.Rollback(); } catch { /* best effort */ }
            throw;
        }
    }
    
    public async ValueTask DisposeAsync()
    {
        await Task.CompletedTask;
        GC.SuppressFinalize(this);
    }
}