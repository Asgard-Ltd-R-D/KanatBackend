using PacketProcessing.Entities;
using PacketProcessing.Utils.Enums;
using QuestDB.Senders;

namespace PacketProcessing.Repositories.InfluxRepository;

public interface IInfluxRepository<T> where T : BasePacketEntity
{
    /// <summary>
    /// Writes a single packet entity to QuestDB using the provided sender
    /// </summary>
    /// <param name="sender">The QuestDB sender for writing data</param>
    /// <param name="entity">The packet entity to write</param>
    /// <param name="ct">Cancellation token for the operation</param>
    /// <returns>A task representing the asynchronous write operation</returns>
    /// <exception cref="ArgumentNullException">Thrown when sender or entity is null</exception>
    Task WriteQuestDbAsync(ISender sender, T entity, CancellationToken ct = default);
    
    /// <summary>
    /// Writes a batch of packet entities to QuestDB using the provided sender
    /// </summary>
    /// <param name="sender">The QuestDB sender for writing data</param>
    /// <param name="batch">The collection of packet entities to write</param>
    /// <param name="ct">Cancellation token for the operation</param>
    /// <returns>A task representing the asynchronous batch write operation</returns>
    /// <exception cref="ArgumentNullException">Thrown when sender is null</exception>
    /// <exception cref="ArgumentException">Thrown when batch is empty</exception>
    Task WriteBatchQuestDbAsync(ISender sender, IReadOnlyList<T> batch, CancellationToken ct = default);

    /// <summary>
    /// Truncates the base table (motion, safety, or onvif) removing all packets
    /// </summary>
    /// <returns>A task representing the asynchronous operation</returns>
    Task ClearAllPacketsAsync();
    
    // QuestDB Operations
    /// <summary>
    /// Retrieves all packets from a session table for the specified range ID
    /// </summary>
    /// <param name="rangeId">The range ID to fetch packets from</param>
    /// <returns>A collection of all packets ordered by timestamp (newest first)</returns>
    Task<IEnumerable<T>> GetAllPacketsByRangeAsync(Guid rangeId);
    
    /// <summary>
    /// Retrieves paginated packets within a specified time range from a session table for the specified range ID
    /// </summary>
    /// <param name="rangeId">The range ID to fetch packets from</param>
    /// <param name="startTimestamp">The start timestamp for the query range</param>
    /// <param name="endTimestamp">The end timestamp for the query range</param>
    /// <param name="orderBy">The ordering direction (Ascending or Descending)</param>
    /// <param name="page">The page number (1-based)</param>
    /// <param name="pageSize">The number of items per page</param>
    /// <returns>A collection of packets for the specified page</returns>
    Task<IEnumerable<T>> GetPaginatedPacketsByRangeAsync(
        Guid rangeId,
        DateTime startTimestamp, 
        DateTime endTimestamp, 
        OrderBy orderBy = OrderBy.Asc, 
        int page = 1, 
        int pageSize = 1_000);

    /// <summary>
    /// Retrieves paginated packets within a specified time range from a session table for the specified range ID with a specified interval
    /// </summary>
    /// <param name="rangeId">The range ID to fetch packets from</param>
    /// <param name="startTimestamp">The start timestamp for the query range</param>
    /// <param name="endTimestamp">The end timestamp for the query range</param>
    /// <param name="interval">The interval for the query range in milliseconds</param>
    /// <param name="orderBy">The ordering direction (Ascending or Descending)</param>
    /// <param name="page">The page number (1-based)</param>
    /// <param name="pageSize">The number of items per page</param>
    /// <returns>A collection of packets for the specified page</returns>
    Task<IEnumerable<T>> GetPaginatedPacketsByRangeAsyncWithInterval(
        Guid rangeId,
        DateTime startTimestamp, 
        DateTime endTimestamp,
        int interval,
        OrderBy orderBy = OrderBy.Asc, 
        int page = 1, 
        int pageSize = 1_000);
    
    /// <summary>
    /// Deletes a specific session table by truncating and dropping it
    /// </summary>
    /// <param name="rangeId">The range ID whose session table should be deleted</param>
    /// <returns>A task representing the asynchronous operation</returns>
    Task DeletePacketsByRangeAsync(Guid rangeId);
    
    /// <summary>
    /// Creates a session table for the specified range ID by copying all data from the base table
    /// </summary>
    /// <param name="rangeId">The range ID for the session table</param>
    /// <returns>A task representing the asynchronous operation</returns>
    Task CreateSessionTableAsync(Guid rangeId);
}