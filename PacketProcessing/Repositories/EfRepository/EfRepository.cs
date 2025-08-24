using System.Diagnostics;
using System.Reflection;
using InfluxDB.Client.Core;
using Microsoft.Extensions.Logging;
using Npgsql;
using PacketProcessing.Database;
using PacketProcessing.Entities;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Repositories.EfRepository;

public sealed class EfRepository<T> : IEfRepository<T> where T : BasePacketEntity
{
    private readonly IQuestDbClient _qdb;
    private readonly ILogger<EfRepository<T>> _logger;
    
    // resolved once via a dummy instance
    private static readonly string TableName;
    private static readonly string TimestampColumn;
    private static readonly string SelectList;
    private static readonly string[] ColumnNames;
    
    static EfRepository()
    {
        var t = typeof(T);

        var m = t.GetCustomAttributes(typeof(Measurement), inherit: true)
            .Cast<Measurement>()
            .FirstOrDefault();

        Debug.Assert(m?.Name != null, "m?.Name != null");
        TableName = m.Name;

        // Columns from [Column] attributes
        var props = t.GetProperties(BindingFlags.Instance | BindingFlags.Public);
        var cols = new List<(PropertyInfo Prop, string SqlName, bool IsTimestamp)>();
        foreach (var p in props)
        {
            var col = p.GetCustomAttributes(typeof(Column), true)
                .Cast<Column>()
                .FirstOrDefault();
            if (col is null) continue;
            var sqlName = string.IsNullOrWhiteSpace(col.Name) ? p.Name : col.Name;
            cols.Add((p, sqlName, col.IsTimestamp));
        }

        if (!cols.Any(c => c.IsTimestamp))
            throw new InvalidOperationException($"{t.Name} must have a [Column(..., IsTimestamp = true)] property.");

        TimestampColumn = cols.First(c => c.IsTimestamp).SqlName;
        ColumnNames = cols.Select(c => c.SqlName).ToArray();
        SelectList = string.Join(", ", ColumnNames.Select(Q => Q));
    }
    
    public EfRepository(IQuestDbClient qdb, ILogger<EfRepository<T>> logger)
    {
        _qdb = qdb ?? throw new ArgumentNullException(nameof(qdb));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }
    
    public async Task<IEnumerable<T>> GetAllPacketsAsync()
    {
        var sql = $"select {SelectList} from \"{TableName}\" order by \"{TimestampColumn}\" asc";
        _logger.LogInformation("QuestDB SELECT all: {Sql}", sql);
        return await _qdb.QueryAsync(sql, ProjectRow);
    }
    
    public async Task DeleteAllPacketsAsync()
    {
        var sql = $"truncate table \"{TableName}\"";
        _logger.LogWarning("QuestDB TRUNCATE: {Sql}", sql);
        await _qdb.ExecuteAsync(sql);
    }

    public async Task<IEnumerable<T>> GetPaginatedPacketsBetweenTimestampsAsync(
        DateTime startTimestamp,
        DateTime endTimestamp,
        OrderBy orderBy = OrderBy.Asc,
        int page = 1,
        int pageSize = 1_000)
    {
        if (page < 1) page = 1;
        if (pageSize < 1) pageSize = 1;

        var dir = orderBy == OrderBy.Desc ? "desc" : "asc";
        var offset = (page - 1) * pageSize;

        // Build SQL (parameter-less, but safe: we only inline numbers and quoted idents)
        var sql =
            $"select {SelectList} " +
            $"from {TableName} " +
            $"where {TimestampColumn} between to_timestamp({startTimestamp}) and to_timestamp({endTimestamp}) " +
            $"order by {TimestampColumn} {dir} " +
            $"limit {pageSize} offset {offset}";

        _logger.LogInformation("QuestDB SELECT (paged): {Sql}", sql);

        // Reflection projector (inline; no helpers)
        return await _qdb.QueryAsync(sql, ProjectRow);
    }
    
    // --- helpers ---
    
    private static T ProjectRow(NpgsqlDataReader rd)
    {
        var obj = (T)Activator.CreateInstance(typeof(T))!;
        var props = typeof(T).GetProperties(BindingFlags.Instance | BindingFlags.Public);

        foreach (var p in props)
        {
            // Look up [Column("name")] attribute, fallback to property name
            var influxCol = p.GetCustomAttributes(typeof(Column), true)
                             .Cast<Column>()
                             .FirstOrDefault();
            var colName = influxCol?.Name ?? p.Name;

            var idx = Ordinal(colName);
            if (idx < 0 || rd.IsDBNull(idx)) continue;

            var target = Nullable.GetUnderlyingType(p.PropertyType) ?? p.PropertyType;
            object? value;

            if (target == typeof(string))
                value = rd.GetString(idx);
            else if (target == typeof(Guid))
            {
                var s = rd.GetString(idx);
                value = Guid.TryParse(s, out var g) ? g : Guid.Empty;
            }
            else if (target == typeof(bool))
                value = rd.GetBoolean(idx);
            else if (target == typeof(int))
                value = rd.GetInt32(idx);
            else if (target == typeof(long))
                value = rd.GetInt64(idx);
            else if (target == typeof(float))
                value = Convert.ToSingle(rd.GetDouble(idx));
            else if (target == typeof(double))
                value = rd.GetDouble(idx);
            else if (target == typeof(decimal))
                value = Convert.ToDecimal(rd.GetDouble(idx));
            else if (target == typeof(DateTime))
                value = rd.GetFieldValue<DateTime>(idx);
            else if (target == typeof(DateTimeOffset))
                value = rd.GetFieldValue<DateTimeOffset>(idx);
            else
                continue; // unsupported → skip

            p.SetValue(obj, value);
        }

        return obj;

        // local helper for case-insensitive column ordinal lookup
        int Ordinal(string name)
        {
            for (var i = 0; i < rd.FieldCount; i++)
                if (string.Equals(rd.GetName(i), name, StringComparison.OrdinalIgnoreCase))
                    return i;
            return -1;
        }
    }
}