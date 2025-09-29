using Dapper;
using Microsoft.Extensions.Logging;
using PacketProcessing.Context;
using PacketProcessing.Entities;
using PacketProcessing.Utils.Enums;
using QuestDB.Senders;

namespace PacketProcessing.Repositories.InfluxRepository;

/// <summary>
/// Generic repository implementation for packet-specific operations
/// Extends EfRepository and InfluxRepository to provide both EF Core and InfluxDB operations
/// along with packet-specific query methods
/// </summary>
/// <typeparam name="T">The type of packet entity (must inherit from BasePacketEntity)</typeparam>
public class InfluxRepository<T> : IInfluxRepository<T> where T : BasePacketEntity
{
    private readonly ILogger<InfluxRepository<T>> _logger;
    private readonly QuestDbContext _questDb;
    
    public InfluxRepository(ILogger<InfluxRepository<T>> logger,
                            QuestDbContext questDbContext)
    {
        _logger  = logger ?? throw new ArgumentNullException(nameof(logger));
        _questDb = questDbContext ?? throw new ArgumentNullException(nameof(questDbContext));
    }
    
    /// <summary>
    /// Writes a single packet entity to QuestDB using the provided sender
    /// Maps the entity to a QuestDB row and commits it in a transaction
    /// </summary>
    /// <param name="sender">The QuestDB sender for writing data</param>
    /// <param name="entity">The packet entity to write</param>
    /// <param name="ct">Cancellation token for the operation</param>
    /// <returns>A task representing the asynchronous write operation</returns>
    /// <exception cref="ArgumentNullException">Thrown when sender or entity is null</exception>
    public async Task WriteQuestDbAsync(ISender sender, T entity, CancellationToken ct = default)
    {
        // Validate input parameters
        ArgumentNullException.ThrowIfNull(entity);
        ArgumentNullException.ThrowIfNull(sender);
        
        try
        {
            _logger.LogDebug("Writing single packet of type {EntityType} with ID {Id} to QuestDB", 
                typeof(T).Name, entity.Id);
            
            // start one transaction for this row
            var table = entity.TableName;
            sender.Transaction(table);
            sender.Symbol("id", entity.Id.ToString("N"));

            entity.WriteColumns(sender);

            // ensure UTC timestamp
            var tsUtc = entity.Timestamp.Kind == DateTimeKind.Utc
                ? entity.Timestamp
                : DateTime.SpecifyKind(entity.Timestamp, DateTimeKind.Utc);

            sender.At(tsUtc, ct);

            // Commit the transaction
            await sender.CommitAsync(ct).ConfigureAwait(false);
            
            _logger.LogInformation("Successfully wrote packet of type {EntityType} with ID {Id} to table {Table}", 
                typeof(T).Name, entity.Id, table);
        } 
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to write packet of type {EntityType} with ID {Id} to QuestDB", 
                typeof(T).Name, entity.Id);
            try 
            { 
                sender.Rollback(); 
                _logger.LogDebug("Successfully rolled back transaction for packet {Id}", entity.Id);
            } 
            catch (Exception rollbackEx)
            { 
                _logger.LogWarning(rollbackEx, "Failed to rollback transaction for packet {Id}", entity.Id);
            }
            throw;
        }
    }

    /// <summary>
    /// Writes a batch of packet entities to QuestDB using the provided sender
    /// Maps entities to QuestDB rows, sorts them by timestamp, and commits them in a transaction
    /// </summary>
    /// <param name="sender">The QuestDB sender for writing data</param>
    /// <param name="batch">The collection of packet entities to write</param>
    /// <param name="ct">Cancellation token for the operation</param>
    /// <returns>A task representing the asynchronous batch write operation</returns>
    /// <exception cref="ArgumentNullException">Thrown when sender is null</exception>
    /// <exception cref="ArgumentException">Thrown when batch is empty</exception>
    public async Task WriteBatchQuestDbAsync(ISender sender, IReadOnlyList<T> batch, CancellationToken ct = default)
    {
        // Validate input parameters
        ArgumentNullException.ThrowIfNull(sender);
        if (batch.Count == 0)
        {
            _logger.LogWarning("Attempted to write empty batch for entity type {EntityType}", typeof(T).Name);
            return;
        }
        
        ct.ThrowIfCancellationRequested();
        
        try
        {
            _logger.LogDebug("Writing batch of {Count} packets of type {EntityType} to QuestDB", 
                batch.Count, typeof(T).Name);
            
            // Create a transaction with the table structure from the first row
            var table = batch[0].TableName;
            sender.Transaction(table);

            for (int i = 0; i < batch.Count; i++)
            {
                ct.ThrowIfCancellationRequested();
                var e = batch[i];
                var tsUtc = e.Timestamp.Kind == DateTimeKind.Utc ? e.Timestamp : DateTime.SpecifyKind(e.Timestamp, DateTimeKind.Utc);

                sender.Symbol("id", e.Id.ToString("N"));
                e.WriteColumns(sender);
                sender.At(tsUtc, ct);
            }

            // Commit the entire batch transaction
            await sender.CommitAsync(ct).ConfigureAwait(false);
            _logger.LogInformation("Successfully wrote batch of packets of type {EntityType} to table {Table}", typeof(T).Name, table);
        } 
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to write batch of {Count} packets of type {EntityType} to QuestDB", 
                batch.Count, typeof(T).Name);
            try 
            { 
                sender.Rollback(); 
                _logger.LogDebug("Successfully rolled back batch transaction for {Count} packets", batch.Count);
            } 
            catch (Exception rollbackEx)
            { 
                _logger.LogWarning(rollbackEx, "Failed to rollback batch transaction for {Count} packets", batch.Count);
            }
            throw;
        }
    }
    
    /// <summary>
    /// Retrieves all packets of the specified type from QuestDB (newest first).
    /// </summary>
    public async Task<IEnumerable<T>> GetAllFromQuestDbAsync()
    {
        try
        {
            _logger.LogDebug("Retrieving all packets of type {EntityType} from QuestDB", typeof(T).Name);

            var table  = QuestDbContext.GetTableName<T>();
            var select = QuestDbContext.SelectListFor<T>();
            var sql = $"""
                SELECT {select}
                FROM {table}
                ORDER BY timestamp DESC
            """;

            await using var conn = await _questDb.OpenPgAsync();

            var rows = await conn.QueryAsync<T>(sql);
            _logger.LogDebug("Retrieved {Count} packets of type {EntityType} from QuestDB", rows.Count(), typeof(T).Name);
            return rows;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error retrieving all packets of type {EntityType} from QuestDB", typeof(T).Name);
            throw;
        }
    }
    
    /// <summary>
    /// Deletes all packets of the specified type from QuestDB.
    /// </summary>
    public async Task DeleteAllFromQuestDbAsync()
    {
        try
        {
            var table = QuestDbContext.GetTableName<T>();
            _logger.LogInformation("Truncating QuestDB table {Table} for {EntityType}", table, typeof(T).Name);

            var sql = $"TRUNCATE TABLE {table}";

            await using var conn = await _questDb.OpenPgAsync();
            await conn.ExecuteAsync(sql);

            _logger.LogInformation("Successfully truncated table {Table} in QuestDB", table);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error truncating QuestDB table for {EntityType}", typeof(T).Name);
            throw;
        }
    }
    
    /// <summary>
    /// Retrieves paginated packets in a time range using OFFSET/LIMIT (simple).
    /// </summary>
    public async Task<IEnumerable<T>> GetPaginatedFromQuestDbAsync(
        DateTime startTimestamp,
        DateTime endTimestamp,
        OrderBy orderBy = OrderBy.Asc,
        int page = 1,
        int pageSize = 1_000)
    {
        try
        {
            if (startTimestamp.Kind != DateTimeKind.Utc || endTimestamp.Kind != DateTimeKind.Utc)
                _logger.LogWarning("QuestDB expects UTC timestamps; got {StartKind}/{EndKind}", startTimestamp.Kind, endTimestamp.Kind);

            _logger.LogDebug(
                "QuestDB page for {EntityType}: {Start:u}..{End:u}, page {Page}, size {Size}",
                typeof(T).Name, startTimestamp, endTimestamp, page, pageSize);

            var table  = QuestDbContext.GetTableName<T>();
            var select = QuestDbContext.SelectListFor<T>();
            var order  = orderBy == OrderBy.Asc ? "ASC" : "DESC";
            var offset = Math.Max(0, (page - 1) * pageSize);

            var lower = Math.Max(0, offset);
            var upper = checked(lower + pageSize); // throws on overflow (defensive)
            var sorder = orderBy == OrderBy.Asc ? "ASC" : "DESC"; // enum -> safe literal

            var sql = $"""
                SELECT {select}
                FROM {table}
                WHERE timestamp >= @start AND timestamp <= @end
                ORDER BY timestamp {sorder}
                LIMIT {lower}, {upper}
            """;

            var args = new { start = startTimestamp, end = endTimestamp };

            await using var conn = await _questDb.OpenPgAsync();

            var rows = await conn.QueryAsync<T>(sql, args);
            _logger.LogDebug("QuestDB page fetched: {Count} rows (page {Page})", rows.Count(), page);
            return rows;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex,
                "Error retrieving paginated packets of type {EntityType} from QuestDB between {StartTimestamp} and {EndTimestamp}",
                typeof(T).Name, startTimestamp, endTimestamp);
            throw;
        }
    }
}
