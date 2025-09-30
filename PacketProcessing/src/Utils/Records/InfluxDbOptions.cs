namespace PacketProcessing.Utils.Records;

/// <summary>
/// Options for connecting to QuestDB via Influx Line Protocol (ILP).
/// Bound from configuration: section "InfluxDb"
/// </summary>
public sealed record InfluxDbOptions
{
    /// <summary>
    /// QuestDB host (default: localhost)
    /// </summary>
    public string Host { get; init; } = "localhost";

    /// <summary>
    /// QuestDB ILP port (default: 9009 for TCP, 9000 for HTTP)
    /// </summary>
    public int Port { get; init; } = 9009;

    /// <summary>
    /// Username for authentication
    /// </summary>
    public string Username { get; init; } = "admin";

    /// <summary>
    /// Password for authentication
    /// </summary>
    public string Password { get; init; } = "quest";

    /// <summary>
    /// Max rows to buffer before flushing (auto_flush_rows)
    /// </summary>
    public int BatchSize { get; init; } = 500;

    /// <summary>
    /// Timeout (ms) before forcing flush even if batch not full (auto_flush_interval)
    /// </summary>
    public int BatchTimeoutMs { get; init; } = 100;
}
