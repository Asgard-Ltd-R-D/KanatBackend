using PacketProcessing.Entities;
using QuestDB.Senders;

namespace PacketProcessing.Repositories.InfluxRepository;

public interface IInfluxRepository<in T> where T : BasePacketEntity
{
    Task WriteAsync(ISender sender, T entity, CancellationToken ct = default);
    
    Task WriteBatchAsync(ISender sender, IReadOnlyList<T> batch, CancellationToken ct = default);
}