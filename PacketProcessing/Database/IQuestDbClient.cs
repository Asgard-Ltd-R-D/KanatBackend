using Npgsql;

namespace PacketProcessing.Database;

public interface IQuestDbClient : IAsyncDisposable
{
    // --- Connection ---
    Task OpenAsync(CancellationToken ct = default);

    // --- Raw SQL ---
    Task<int> ExecuteAsync(string sql, CancellationToken ct = default);
    Task<T?> ExecuteScalarAsync<T>(string sql, CancellationToken ct = default);
    Task<List<T>> QueryAsync<T>(string sql, Func<NpgsqlDataReader, T> projector, CancellationToken ct = default);
}