using System.ComponentModel.DataAnnotations.Schema;
using System.Data;
using System.Reflection;
using Dapper;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Npgsql;

namespace PacketProcessing.Context;

public sealed class QuestDbContext
{
    private readonly ILogger<QuestDbContext> _log;
    public NpgsqlDataSource DataSource { get; }
    public string ConnectionString { get; }

    public QuestDbContext(IConfiguration cfg, ILogger<QuestDbContext> log)
    {
        _log = log;
        var s = cfg.GetSection("QuestDb");

        // Enable legacy timestamp behavior
        AppContext.SetSwitch("Npgsql.EnableLegacyTimestampBehavior", true);

        // Add Guid type handler
        SqlMapper.AddTypeHandler(new GuidAsStringHandler());

        // Add NpgsqlConnectionStringBuilder
        var csb = new NpgsqlConnectionStringBuilder
        {
            Host = s["Host"] ?? "127.0.0.1",
            Port = int.TryParse(s["Port"], out var p) ? p : 8812,
            Username = s["Username"] ?? "quest",
            Password = s["Password"] ?? "quest",
            Database = s["Database"] ?? "qdb",
            NoResetOnClose = true,
            Multiplexing = true,
            MaxPoolSize = 50,
            ServerCompatibilityMode = ServerCompatibilityMode.NoTypeLoading
        };

        ConnectionString = csb.ToString();
        DataSource = NpgsqlDataSource.Create(ConnectionString);
    }

    /// <summary>
    /// Open a connection to the QuestDB database
    /// </summary>
    /// <param name="ct"></param>
    /// <returns></returns>
    public async Task<NpgsqlConnection> OpenPgAsync(CancellationToken ct = default) => await DataSource.OpenConnectionAsync(ct);
    /// <summary>
    /// Dispose the QuestDB database connection
    /// </summary>
    /// <returns></returns>
    public async ValueTask DisposeAsync() => await DataSource.DisposeAsync();

    /// <summary>Just run IF NOT EXISTS DDL as a single batch. Returns true if table count increased.</summary>
    public async Task<bool> EnsureDatabaseAsync(CancellationToken ct = default)
    {
        const string tableList = "'motion_packets','onvif_packets','safety_packets'";
        var ddl = """
        CREATE TABLE IF NOT EXISTS motion_packets (
            timestamp       TIMESTAMP,
            id              SYMBOL,
            isCmd           BOOLEAN,
            opCode          STRING,
            description     STRING,
            axis            INT,
            value           DOUBLE
        ) TIMESTAMP(timestamp) PARTITION BY DAY WAL;

        CREATE TABLE IF NOT EXISTS onvif_packets (
            timestamp          TIMESTAMP,
            id                 SYMBOL,
            isCmd              BOOLEAN,
            description        STRING,
            zoom               DOUBLE,
            measurement        DOUBLE
        ) TIMESTAMP(timestamp) PARTITION BY DAY WAL;

        CREATE TABLE IF NOT EXISTS safety_packets (
            timestamp         TIMESTAMP,
            id                SYMBOL,
            isCmd             BOOLEAN,
            name              STRING,
            opCode            STRING,
            description       STRING,
            state             STRING
        ) TIMESTAMP(timestamp) PARTITION BY DAY WAL;
        """;

        await using var conn = await OpenPgAsync(ct);

        var before = await conn.ExecuteScalarAsync<long>(
            new CommandDefinition($"SELECT count(*) FROM information_schema.tables WHERE table_name IN ({tableList})", cancellationToken: ct));

        try
        {
            _log.LogDebug("Executing DDL to create QuestDB tables...");
            await conn.ExecuteAsync(new CommandDefinition(ddl, cancellationToken: ct));
        }
        catch (Exception ex)
        {
            _log.LogError(ex, "Failed to create QuestDB tables. DDL: {DDL}", ddl);
            throw;
        }

        var after = await conn.ExecuteScalarAsync<long>(
            new CommandDefinition($"SELECT count(*) FROM information_schema.tables WHERE table_name IN ({tableList})", cancellationToken: ct));

        var created = after > before;
        _log.LogInformation(created
            ? "QuestDB: one or more tables were created."
            : "QuestDB: all tables already exist.");
        return created;
    }

    /// <summary>Resolve table name from [Table("...")] or fallback to type name.</summary>
    public static string GetTableName<T>()
        => typeof(T).GetCustomAttribute<TableAttribute>()?.Name
           ?? typeof(T).Name;

    /// <summary>
    /// Auto-builds SELECT list by reflecting properties and their [Column] names.
    /// Ensures Dapper maps db_column AS "PropertyName".
    /// Excludes properties that don't have database columns (like TableName).
    /// </summary>
    public static string SelectListFor<T>()
    {
        var props = typeof(T).GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Where(p => p.CanRead)
            .Where(p => p.GetCustomAttribute<ColumnAttribute>() != null) // Only include properties with [Column] attribute
            .Select(p =>
            {
                var col = p.GetCustomAttribute<ColumnAttribute>()!.Name;
                return $"{col} as \"{p.Name}\"";
            });

        return string.Join(", ", props);
    }

    /// <summary>
    /// Handles Guid type conversion for QuestDB
    /// </summary>
    private sealed class GuidAsStringHandler : SqlMapper.TypeHandler<Guid>
    {
        public override void SetValue(IDbDataParameter parameter, Guid value)
            => parameter.Value = value.ToString("N"); // 32-char hex without dashes

        public override Guid Parse(object value)
        {
            if (value is null || value is DBNull) return Guid.Empty; // or throw if you prefer
            if (value is Guid g) return g;
            if (value is string s && Guid.TryParse(s, out var parsed)) return parsed;
            if (value is byte[] bytes && bytes.Length == 16) return new Guid(bytes);
            return Guid.Parse(value.ToString()!);
        }
    }
}
