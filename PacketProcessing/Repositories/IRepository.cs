using PacketProcessing.Model;

namespace PacketProcessing.Repositories;

public interface IRepository<in TEntity> where TEntity : BasePacket
{
    Task AddSingleAsync(TEntity packet, CancellationToken ct = default);
    Task AddBatchAsync(IReadOnlyList<TEntity> batch, CancellationToken ct = default);
}