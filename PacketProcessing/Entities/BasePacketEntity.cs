using InfluxDB.Client.Core;
using PacketProcessing.Utils.QuestDB;
using QuestDB.Senders;

namespace PacketProcessing.Entities;

public abstract class BasePacketEntity : IQuestDbMappable
{
    [Column("id", IsTag = true)]
    public Guid Id { get; set; } = Guid.NewGuid();
    
    [Column("timestamp", IsTimestamp = true)]
    public required DateTime Timestamp { get; set; } = DateTime.UtcNow;
    
    
    protected abstract string MeasurementName { get; }
    
    protected abstract void WriteColumns(ISender sender);
    
    // ---- QuestDbMappable ----
    public string QuestTable => MeasurementName;
    public string QuestTimestampColumn => "timestamp";

    public virtual IReadOnlyList<(string Name, string Type, bool IsSymbol, bool Indexed)> GetQuestColumns()
        => new (string, string, bool, bool)[]
        {
            // “id” is a tag → SYMBOL is ideal; index it for fast filters
            ("id", "SYMBOL", isSymbol: true, indexed: true),

            // designated timestamp column stored as TIMESTAMP
            ("timestamp", "TIMESTAMP", isSymbol: false, indexed: false),
        };
    
    // ---- ILP write ----
    public virtual RowMap ToRowMap()
    {
        var table = MeasurementName;
        var tsUtc = DateTime.SpecifyKind(Timestamp, DateTimeKind.Utc);

        return new RowMap(
            table,
            tsUtc,
            apply: sender =>
            {
                sender
                    .Table(table)
                    .Symbol("id", Id.ToString("N"));

                WriteColumns(sender);

                sender.At(tsUtc);
            });
    }
}