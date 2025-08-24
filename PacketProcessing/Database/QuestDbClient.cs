using System.Data;
using System.Text;
using Npgsql;

namespace PacketProcessing.Database;

public class QuestDbClient : IQuestDbClient
{
    private readonly NpgsqlConnection _conn;

    public QuestDbClient(string connectionString)
    {
        _conn = new NpgsqlConnection(connectionString);
    }
    
    // --- Connection ---
    
    public async Task OpenAsync(CancellationToken ct = default)
    {
        if (_conn.State != ConnectionState.Open)
            await _conn.OpenAsync(ct);
    }

    // --- Raw SQL ---

    public async Task<int> ExecuteAsync(string sql, CancellationToken ct = default)
    {
        await OpenAsync(ct);
        await using var cmd = new NpgsqlCommand(sql, _conn);
        return await cmd.ExecuteNonQueryAsync(ct);
    }

    public async Task<T?> ExecuteScalarAsync<T>(string sql, CancellationToken ct = default)
    {
        await OpenAsync(ct);
        await using var cmd = new NpgsqlCommand(sql, _conn);
        var r = await cmd.ExecuteScalarAsync(ct);
        if (r is null or DBNull) return default;
        
        var target = typeof(T);
        var underlying = Nullable.GetUnderlyingType(target);

        if (underlying is not null)
        {
            // e.g. T == long? and r is Int32(1) → convert to Int64 then box to long?
            var converted = Convert.ChangeType(r, underlying, System.Globalization.CultureInfo.InvariantCulture);
            return (T)(object)converted!;
        }
        
        return (T)Convert.ChangeType(r, target, System.Globalization.CultureInfo.InvariantCulture);
    }

    public async Task<List<T>> QueryAsync<T>(string sql, Func<NpgsqlDataReader, T> projector, CancellationToken ct = default)
    {
        await OpenAsync(ct);
        var list = new List<T>();
        await using var cmd = new NpgsqlCommand(sql, _conn);
        await using var rd = await cmd.ExecuteReaderAsync(ct);
        while (await rd.ReadAsync(ct))
            list.Add(projector(rd));
        return list;
    }

    public async ValueTask DisposeAsync()
    {
        await _conn.DisposeAsync();
        GC.SuppressFinalize(this);
    }
}