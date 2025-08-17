namespace PacketProcessing.Configuration;

public class QuestDbOptions
{
    public const string SectionName = "QuestDB";
    
    public string Host { get; set; } = "localhost";
    public int Port { get; set; } = 8812;
    public string Username { get; set; } = "quest";
    public string Password { get; set; } = "quest";
    public string Database { get; set; } = "qdb";
    public int BatchSize { get; set; } = 100;
    public int BatchTimeoutMs { get; set; } = 30;
}
