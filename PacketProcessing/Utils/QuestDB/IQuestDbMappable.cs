namespace PacketProcessing.Utils.QuestDB;

public interface IQuestDbMappable
{
    // Table (measurement) name in QuestDB
    string QuestTable { get; }

    // Designated timestamp column name in QuestDB (use your "timestamp")
    string QuestTimestampColumn { get; }

    // Full column list (name, type) that should exist in QuestDB
    // Types are QuestDB SQL types: SYMBOL, STRING, BOOLEAN, INT, LONG, DOUBLE, TIMESTAMP
    IReadOnlyList<(string Name, string Type, bool IsSymbol, bool Indexed)> GetQuestColumns();
}