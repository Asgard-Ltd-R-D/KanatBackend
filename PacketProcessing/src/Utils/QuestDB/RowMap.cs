using QuestDB.Senders;

namespace PacketProcessing.Utils.QuestDB;

public sealed class RowMap
{
    public string Table { get; }
    public DateTime TimestampUtc { get; }
    private readonly Action<ISender> _apply;
    
    public RowMap(string table, DateTime timestampUtc, Action<ISender> apply)
    {
        Table = table ?? throw new ArgumentNullException(nameof(table));
        TimestampUtc = DateTime.SpecifyKind(timestampUtc, DateTimeKind.Utc);
        _apply = apply ?? throw new ArgumentNullException(nameof(apply));
    }
    
    public void Apply(ISender sender) => _apply(sender);
}