using PacketProcessing.Entities;
using PacketProcessing.Utils.Enums;
using QuestDB.Senders;

namespace PacketProcessing.Repositories.InfluxRepository;

public interface IInfluxRepository<T> where T : BasePacketEntity
{
    // QuestDB Operations
    /// <summary>
    /// Retrieves all packets of the specified type from QuestDB
    /// </summary>
    /// <returns>A collection of all packets ordered by timestamp (newest first)</returns>
    Task<IEnumerable<T>> GetAllFromQuestDbAsync();
    
    /// <summary>
    /// Deletes all packets of the specified type from QuestDB
    /// </summary>
    /// <returns>A task representing the asynchronous operation</returns>
    Task DeleteAllFromQuestDbAsync();
    
    /// <summary>
    /// Retrieves paginated packets within a specified time range from QuestDB
    /// </summary>
    /// <param name="startTimestamp">The start timestamp for the query range</param>
    /// <param name="endTimestamp">The end timestamp for the query range</param>
    /// <param name="orderBy">The ordering direction (Ascending or Descending)</param>
    /// <param name="page">The page number (1-based)</param>
    /// <param name="pageSize">The number of items per page</param>
    /// <returns>A collection of packets for the specified page</returns>
    Task<IEnumerable<T>> GetPaginatedFromQuestDbAsync(
        DateTime startTimestamp, 
        DateTime endTimestamp, 
        OrderBy orderBy = OrderBy.Asc, 
        int page = 1, 
        int pageSize = 1_000);

    /// <summary>
    /// Retrieves paginated packets within a specified time range from QuestDB with a specified interval
    /// </summary>
    /// <param name="startTimestamp">The start timestamp for the query range</param>
    /// <param name="endTimestamp">The end timestamp for the query range</param>
    /// <param name="interval">The interval for the query range in milliseconds</param>
    /// <param name="orderBy">The ordering direction (Ascending or Descending)</param>
    /// <param name="page">The page number (1-based)</param>
    /// <param name="pageSize">The number of items per page</param>
    /// <returns>A collection of packets for the specified page</returns>
    Task<IEnumerable<T>> GetPaginatedFromQuestDbAsyncWithInterval(
    DateTime startTimestamp, 
    DateTime endTimestamp,
    int interval,
    OrderBy orderBy = OrderBy.Asc, 
    int page = 1, 
    int pageSize = 1_000);
    
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
    /// Clears packets of the specified type from QuestDB within a specified time range
    /// </summary>
    /// <param name="start">The start timestamp for the query range</param>
    /// <param name="end">The end timestamp for the query range</param>
    /// <returns>A task representing the asynchronous operation</returns>
    Task ClearPacketsByRangeAsync(long start, long end);
}