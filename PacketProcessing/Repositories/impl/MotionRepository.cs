
namespace PacketProcessing.Repositories;

public class MotionRepository : IRepository<MotionPacket>
{
    public Task AddBatchAsync(IReadOnlyList<MotionPacket> batch, CancellationToken ct = default)
    {
        throw new NotImplementedException();
    }

    public Task AddSingleAsync(MotionPacket packet, CancellationToken ct = default)
    {
        throw new NotImplementedException();
    }
}