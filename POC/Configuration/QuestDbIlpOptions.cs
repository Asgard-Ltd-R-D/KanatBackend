namespace PacketProcessing.Configuration;

    public class QuestDbIlpOptions
    {
        public const string SectionName = "QuestDB";
        
        public string Host { get; set; } = "localhost";
        public int Port { get; set; } = 9009; // QuestDB ILP port (per compose)
        public int PostgresPort { get; set; } = 8812; // QuestDB Postgres port (per compose)
        public string Username { get; set; } = "quest";
        public string Password { get; set; } = "quest";
        public string Database { get; set; } = "qdb";
        public string Organization { get; set; } = "my-org";
        public string Bucket { get; set; } = "packets";
        public int BatchSize { get; set; } = 1000;
        public int BatchTimeoutMs { get; set; } = 30;
    }
