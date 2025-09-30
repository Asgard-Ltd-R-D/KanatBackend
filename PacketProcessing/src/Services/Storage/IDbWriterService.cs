using PacketProcessing.Entities;

namespace PacketProcessing.Services.Storage;

/// <summary>
/// Consumes parsed packets from a channel and writes them to QuestDB.
/// </summary>
/// <typeparam name="T">Packet entity type</typeparam>
public interface IDbWriterService<T>
    where T : BasePacketEntity
{
    /// <summary>
    /// Flushes any buffered packets immediately.
    /// </summary>
    Task FlushBatchAsync(CancellationToken ct = default);

    /// <summary>
    /// Get statistics about flushed batches.
    /// </summary>
    (long Flushed, long Failed) GetStats();
}
