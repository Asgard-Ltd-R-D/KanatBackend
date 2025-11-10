using PacketProcessing.Entities;

namespace PacketProcessing.Services.Realtime.Storage;

/// <summary>
/// Consumes parsed packets from a channel and writes them to QuestDB.
/// </summary>
/// <typeparam name="T">Packet entity type</typeparam>
public interface IDbWriterService<T>
    where T : BasePacketEntity
{
    /// <summary>
    /// Get statistics about flushed batches.
    /// </summary>
    (long Flushed, long Failed, double AvgLatencyMs) GetStats();
    
    /// <summary>
    /// Gets the approximate current count of items in the channel waiting to be written.
    /// </summary>
    int GetChannelCount();
    
    /// <summary>
    /// Resets all statistics counters to zero.
    /// </summary>
    void ResetStats();
}
