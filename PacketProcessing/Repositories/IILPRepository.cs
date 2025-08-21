using QuestDB.Senders;

namespace PacketProcessing.Repositories;

public interface IILPRepository<in T> where T : class
{
    string ILPConnectionString { get; }
    Task InsertBatchAsync(ISender sender, IReadOnlyList<T> batch, CancellationToken ct = default);
}