using System.Globalization;
using System.Text;
using PacketProcessing.Entities;

namespace PacketProcessing.Database;

public static class QuestDbSchemaBootstrapper
{
    public static async Task EnsureAllPacketTablesAsync(IQuestDbClient qdb, string partitionBy = "DAY",
        CancellationToken ct = default)
    {
        await qdb.OpenAsync(ct);

        var types = typeof(BasePacketEntity).Assembly.GetTypes()
            .Where(t => t is { IsClass: true, IsAbstract: false } && typeof(BasePacketEntity).IsAssignableFrom(t))
            .ToList();

        if (types.Count == 0)
            throw new InvalidOperationException("No packet entities found.");

        foreach (var t in types)
        {
            ct.ThrowIfCancellationRequested();

            var entity = (BasePacketEntity)Activator.CreateInstance(t)!;
            var table = entity.QuestTable; // e.g. motion_packets
            var tsCol = entity.QuestTimestampColumn; // e.g. timestamp
            var cols = entity.GetQuestColumns(); // (Name, Type, IsSymbol, Indexed)

            // Does table exist? (tables() has columns: table_name, designatedTimestamp, ...)
            var existsSql =
                $"select 1 from tables() where \"table_name\" = '{Escape(table)}' limit 1";
            var exists = await qdb.ExecuteScalarAsync<int?>(existsSql, ct) == 1;

            if (!exists)
            {
                var create = BuildCreateTableSql(table, tsCol, cols, partitionBy);
                await qdb.ExecuteAsync(create, ct);
                continue;
            }

            // Ensure missing columns (table_columns('<table>') exposes a column literally named "column")
            var existing = await qdb.QueryAsync(
                $"select \"column\" from table_columns('{Escape(table)}')",
                r => r.GetString(0), ct);

            var existingSet = new HashSet<string>(existing, StringComparer.OrdinalIgnoreCase);
            foreach (var (name, type, isSymbol, indexed) in cols)
            {
                if (existingSet.Contains(name)) continue;
                var alter = $"ALTER TABLE {Q(table)} ADD COLUMN {BuildColumnDDL(name, type, isSymbol, indexed)};";
                await qdb.ExecuteAsync(alter, ct);
            }
        }
    }

    private static string BuildCreateTableSql(string table, string ts,
        IReadOnlyList<(string Name, string Type, bool IsSymbol, bool Indexed)> cols, string partitionBy)
    {
        var sb = new StringBuilder();
        sb.Append("CREATE TABLE ").Append(Q(table)).Append(" (");
        for (int i = 0; i < cols.Count; i++)
        {
            if (i > 0) sb.Append(", ");
            sb.Append(BuildColumnDDL(cols[i].Name, cols[i].Type, cols[i].IsSymbol, cols[i].Indexed));
        }

        sb.Append(") TIMESTAMP(").Append(Q(ts)).Append(')')
            .Append(" PARTITION BY ").Append(partitionBy).Append(';');
        return sb.ToString();
    }

    private static string BuildColumnDDL(string name, string type, bool isSymbol, bool indexed)
    {
        var sb = new StringBuilder();
        sb.Append(Q(name)).Append(' ').Append(type);

        // Only SYMBOL columns support CACHE / INDEX
        if (string.Equals(type, "SYMBOL", StringComparison.OrdinalIgnoreCase))
        {
            if (isSymbol) sb.Append(" CACHE"); // optional but fine
            if (indexed)  sb.Append(" INDEX");
        }

        return sb.ToString();
    }

    private static string Q(string ident) => "\"" + ident.Replace("\"", "\"\"") + "\"";
    private static string Escape(string s) => s.Replace("'", "''");
}
