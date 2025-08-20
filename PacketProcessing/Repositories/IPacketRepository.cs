namespace PacketProcessing.Repositories;

public interface IPacketRepository<T> where T : BasePacket
{
    Task AddSingleAsync(T packet, CancellationToken ct = default);
    Task AddBatchAsync(IReadOnlyList<T> batch, CancellationToken ct = default);
}