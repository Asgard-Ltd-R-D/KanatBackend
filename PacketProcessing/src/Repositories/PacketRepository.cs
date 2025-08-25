using Microsoft.Extensions.Logging;
using PacketProcessing.Context;
using PacketProcessing.Entities;
using PacketProcessing.Utils.Enums;
using PacketProcessing.Utils.QuestDB;
using QuestDB.Senders;
using Npgsql;

namespace PacketProcessing.Repositories;

/// <summary>
/// Generic repository implementation for packet-specific operations
/// Extends EfRepository and InfluxRepository to provide both EF Core and InfluxDB operations
/// along with packet-specific query methods
/// </summary>
/// <typeparam name="T">The type of packet entity (must inherit from BasePacketEntity)</typeparam>
public class PacketRepository<T> : IPacketRepository<T> where T : BasePacketEntity
{
    private readonly ILogger<PacketRepository<T>> _logger;
    private readonly string _questDbConnectionString;
    
    public PacketRepository(AppDbContext context, ILogger<PacketRepository<T>> logger, string questDbConnectionString) 
    {
        _questDbConnectionString = questDbConnectionString ?? throw new ArgumentNullException(nameof(questDbConnectionString));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
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
            
            // Map entity to QuestDB row using PacketRowMapper
            var row = PacketRowMapper<T>.Map(entity);

            // Create a transaction with the table structure from the row
            var table = row.Table;
            sender.Transaction(table);

            // Apply the row to the sender
            row.Apply(sender);

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
            
            // Sort batch by timestamp for optimal performance
            var rows = batch
                .Select(PacketRowMapper<T>.Map)
                .OrderBy(r => r.TimestampUtc)
                .ToList();

            // Create a transaction with the table structure from the first row
            var table = rows[0].Table;
            sender.Transaction(table);

            // Apply each row to the sender
            foreach (var row in rows)
            {
                ct.ThrowIfCancellationRequested();
                row.Apply(sender); // Append to transaction, no commit yet
            }

            // Commit the entire batch transaction
            await sender.CommitAsync(ct).ConfigureAwait(false);
            
            _logger.LogInformation("Successfully wrote batch of {Count} packets of type {EntityType} to table {Table}", 
                rows.Count, typeof(T).Name, table);
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
    /// Retrieves all packets of the specified type from QuestDB using PostgreSQL wire protocol
    /// </summary>
    /// <returns>A collection of all packets ordered by timestamp (newest first)</returns>
    public async Task<IEnumerable<T>> GetAllFromQuestDbAsync()
    {
        try
        {
            _logger.LogDebug("Retrieving all packets of type {EntityType} from QuestDB", typeof(T).Name);
            
            var tableName = QuestDbUtilities.GetTableName<T>();
            var query = $"SELECT * FROM {tableName} ORDER BY timestamp DESC";
            
            var result = new List<T>();
            using var connection = new NpgsqlConnection(_questDbConnectionString);
            await connection.OpenAsync();
            
            using var command = new NpgsqlCommand(query, connection);
            using var reader = await command.ExecuteReaderAsync();
            
            while (await reader.ReadAsync())
            {
                var entity = QuestDbUtilities.MapReaderToEntity<T>(reader);
                result.Add(entity);
            }
                
            _logger.LogDebug("Retrieved {Count} packets of type {EntityType} from QuestDB", result.Count, typeof(T).Name);
            return result;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error retrieving all packets of type {EntityType} from QuestDB", typeof(T).Name);
            throw;
        }
    }
    
    /// <summary>
    /// Deletes all packets of the specified type from QuestDB
    /// </summary>
    /// <returns>A task representing the asynchronous operation</returns>
    public async Task DeleteAllFromQuestDbAsync()
    {
        try
        {
            _logger.LogInformation("Deleting all packets of type {EntityType} from QuestDB", typeof(T).Name);
            
            var tableName = QuestDbUtilities.GetTableName<T>();
            var query = $"DELETE FROM {tableName}";
            
            using var connection = new NpgsqlConnection(_questDbConnectionString);
            await connection.OpenAsync();
            
            using var command = new NpgsqlCommand(query, connection);
            var affectedRows = await command.ExecuteNonQueryAsync();
            
            _logger.LogInformation("Deleted {Count} packets of type {EntityType} from QuestDB", affectedRows, typeof(T).Name);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error deleting all packets of type {EntityType} from QuestDB", typeof(T).Name);
            throw;
        }
    }
    
    /// <summary>
    /// Retrieves paginated packets within a specified time range from QuestDB
    /// </summary>
    /// <param name="startTimestamp">The start timestamp for the query range</param>
    /// <param name="endTimestamp">The end timestamp for the query range</param>
    /// <param name="orderBy">The ordering direction (Ascending or Descending)</param>
    /// <param name="page">The page number (1-based)</param>
    /// <param name="pageSize">The number of items per page</param>
    /// <returns>A collection of packets for the specified page</returns>
    public async Task<IEnumerable<T>> GetPaginatedFromQuestDbAsync(
        DateTime startTimestamp,
        DateTime endTimestamp,
        OrderBy orderBy = OrderBy.Asc,
        int page = 1,
        int pageSize = 1_000)
    {
        try
        {
            _logger.LogDebug("Retrieving paginated packets of type {EntityType} from QuestDB between {StartTimestamp} and {EndTimestamp}, page {Page}, size {PageSize}", 
                typeof(T).Name, startTimestamp, endTimestamp, page, pageSize);
            
            var tableName = QuestDbUtilities.GetTableName<T>();
            var orderClause = orderBy == OrderBy.Asc ? "ASC" : "DESC";
            var skip = (page - 1) * pageSize;
            
            var query = $@"
                SELECT * FROM {tableName} 
                WHERE timestamp >= @startTimestamp AND timestamp <= @endTimestamp 
                ORDER BY timestamp {orderClause} 
                LIMIT @pageSize OFFSET @skip";
            
            var result = new List<T>();
            using var connection = new NpgsqlConnection(_questDbConnectionString);
            await connection.OpenAsync();
            
            using var command = new NpgsqlCommand(query, connection);
            command.Parameters.AddWithValue("@startTimestamp", startTimestamp);
            command.Parameters.AddWithValue("@endTimestamp", endTimestamp);
            command.Parameters.AddWithValue("@pageSize", pageSize);
            command.Parameters.AddWithValue("@skip", skip);
            
            using var reader = await command.ExecuteReaderAsync();
            while (await reader.ReadAsync())
            {
                var entity = QuestDbUtilities.MapReaderToEntity<T>(reader);
                result.Add(entity);
            }
                
            _logger.LogDebug("Retrieved {Count} packets of type {EntityType} from QuestDB for page {Page}", 
                result.Count, typeof(T).Name, page);
            return result;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error retrieving paginated packets of type {EntityType} from QuestDB between {StartTimestamp} and {EndTimestamp}", 
                typeof(T).Name, startTimestamp, endTimestamp);
            throw;
        }
    }
}
