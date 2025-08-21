using QuestDB.Senders;

namespace PacketProcessing.Repositories;

public interface IILPRepository<T> where T : class
{
    Task InsertBatchAsync(ISender sender, IReadOnlyList<T> batch, CancellationToken ct = default);
}