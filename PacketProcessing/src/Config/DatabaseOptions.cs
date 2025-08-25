namespace PacketProcessing.Config;

/// <summary>
/// Configuration options for PostgreSQL database connection
/// </summary>
public class PostgresOptions
{
    public const string SectionName = "Postgres";
    
    /// <summary>
    /// PostgreSQL server hostname or IP address
    /// </summary>
    public string Host { get; set; } = "localhost";
    
    /// <summary>
    /// PostgreSQL server port
    /// </summary>
    public int Port { get; set; } = 5432;
    
    /// <summary>
    /// Database name
    /// </summary>
    public string Database { get; set; } = "packet_processing";
    
    /// <summary>
    /// Database username
    /// </summary>
    public string Username { get; set; } = "packet_user";
    
    /// <summary>
    /// Database password
    /// </summary>
    public string Password { get; set; } = "packet_password";
    
    /// <summary>
    /// Maximum number of connections in the pool
    /// </summary>
    public int MaxPoolSize { get; set; } = 100;
    
    /// <summary>
    /// Minimum number of connections in the pool
    /// </summary>
    public int MinPoolSize { get; set; } = 5;
    
    /// <summary>
    /// Connection timeout in seconds
    /// </summary>
    public int CommandTimeout { get; set; } = 30;
    
    /// <summary>
    /// Gets the PostgreSQL connection string
    /// </summary>
    /// <returns>The formatted connection string</returns>
    public string GetConnectionString()
    {
        return $"Host={Host};Port={Port};Database={Database};Username={Username};Password={Password};" +
               $"MaxPoolSize={MaxPoolSize};MinPoolSize={MinPoolSize};CommandTimeout={CommandTimeout};" +
               "Include Error Detail=true;";
    }
}

/// <summary>
/// Configuration options for QuestDB connection
/// </summary>
public class QuestDbOptions
{
    public const string SectionName = "QuestDb";
    
    /// <summary>
    /// QuestDB server hostname or IP address
    /// </summary>
    public string Host { get; set; } = "localhost";
    
    /// <summary>
    /// QuestDB PostgreSQL wire protocol port
    /// </summary>
    public int PostgresPort { get; set; } = 9009;
    
    /// <summary>
    /// QuestDB InfluxDB line protocol port
    /// </summary>
    public int InfluxPort { get; set; } = 9000;
    
    /// <summary>
    /// QuestDB HTTP port
    /// </summary>
    public int HttpPort { get; set; } = 8812;
    
    /// <summary>
    /// Database username
    /// </summary>
    public string Username { get; set; } = "quest";
    
    /// <summary>
    /// Database password
    /// </summary>
    public string Password { get; set; } = "quest";
    
    /// <summary>
    /// Database name
    /// </summary>
    public string Database { get; set; } = "qdb";
    
    /// <summary>
    /// Gets the QuestDB PostgreSQL connection string
    /// </summary>
    /// <returns>The formatted connection string</returns>
    public string GetPostgresConnectionString()
    {
        return $"Host={Host};Port={PostgresPort};Database={Database};Username={Username};Password={Password};" +
               "Include Error Detail=true;";
    }
    
    /// <summary>
    /// Gets the QuestDB InfluxDB line protocol connection string
    /// </summary>
    /// <returns>The formatted connection string</returns>
    public string GetInfluxConnectionString()
    {
        return $"http://{Host}:{InfluxPort}";
    }
    
    /// <summary>
    /// Gets the QuestDB HTTP connection string
    /// </summary>
    /// <returns>The formatted connection string</returns>
    public string GetHttpConnectionString()
    {
        return $"http://{Host}:{HttpPort}";
    }
}
