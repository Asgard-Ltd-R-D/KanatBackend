using Microsoft.Extensions.Options;

namespace PacketProcessing.Config;

public class ApplicationOptions 
{
    /// <summary>
    /// Defines the global sniffer configuration.
    /// Contains a list of sniffer pipelines, each describing how packets should be captured.
    /// </summary>
    public sealed class SnifferOptions
    {
        /// <summary>
        /// Section name in configuration (appsettings.json).
        /// </summary>
        public const string SectionName = "Sniffers";

        /// <summary>
        /// A list of sniffer pipelines to run.
        /// Each pipeline specifies its own device, filter, parser, and repository.
        /// </summary>
        public List<SnifferDefinition> Pipelines { get; set; } = new();
    }

    /// <summary>
    /// Represents the configuration of a single sniffer pipeline.
    /// </summary>
    public sealed class SnifferDefinition
    {
        /// <summary>
        /// Logical name of the sniffer (used for logging, metrics, and identification).
        /// </summary>
        public string Name { get; set; } = default!;

        /// <summary>
        /// Network device/interface to capture packets from.
        /// Example: "any", "eth0", "wlan0".
        /// </summary>
        public string Device { get; set; } = "any";

        /// <summary>
        /// Packet filter expression (BPF syntax).
        /// Example: "udp", "tcp port 80".
        /// </summary>
        public string Filter { get; set; } = "udp";

        public static implicit operator SnifferDefinition(IOptions<SnifferDefinition> v)
        {
            throw new NotImplementedException();
        }
    }

    /// <summary>
    /// Configures the packet buffering channels that sit between sniffers (producers)
    /// and workers (consumers).
    /// </summary>
    public sealed class ChannelOptions
    {
        /// <summary>
        /// Section name in configuration (appsettings.json).
        /// </summary>
        public const string SectionName = "Channels";
        
        /// <summary>
        /// Maximum number of packets that can be buffered in the channel before backpressure applies.
        /// </summary>
        public int Capacity { get; set; } = 100_000;

        /// <summary>
        /// Indicates whether the channel has a single reader.
        /// True = only one consumer; False = multiple consumers.
        /// </summary>
        public bool SingleReader { get; set; } = false;

        /// <summary>
        /// Indicates whether the channel has a single writer.
        /// True = only one producer; False = multiple producers.
        /// </summary>
        public bool SingleWriter { get; set; } = false;
    }

    /// <summary>
    /// Worker pool sizing for packet processing.
    /// Workers pull from channels and write batches to the database.
    /// </summary>
    public sealed class WorkerOptions
    {
        /// <summary>
        /// Section name in configuration (appsettings.json).
        /// </summary>
        public const string SectionName = "Workers";

        /// <summary>
        /// Minimum number of worker tasks to keep alive at all times.
        /// </summary>
        public int MinWorkers { get; set; } = 2;

        /// <summary>
        /// Maximum number of worker tasks allowed to scale up under heavy load.
        /// </summary>
        public int MaxWorkers { get; set; } = 8;
    }

    /// <summary>
    /// Database configuration for persisting captured packets.
    /// </summary>
    public sealed class DbOptions
    {
        /// <summary>
        /// Section name in configuration (appsettings.json).
        /// </summary>
        public const string SectionName = "Database";
	
        /// <summary>
        /// Database host address (e.g., "localhost").
        /// </summary>
        public string Host { get; set; } = "localhost";

        /// <summary>
        /// Database port number (e.g., 8086 for InfluxDB).
        /// </summary>
        public int Port { get; set; } = 8086;

        /// <summary>
        /// Username for database authentication.
        /// </summary>
        public string Username { get; set; } = "admin";

        /// <summary>
        /// Password for database authentication.
        /// </summary>
        public string Password { get; set; } = "admin";

        /// <summary>
        /// Logical organization/tenant in the database.
        /// </summary>
        public string Organization { get; set; } = "my-org";

        /// <summary>
        /// Target bucket, measurement, or table where packets will be stored.
        /// </summary>
        public string Bucket { get; set; } = "packets";

        /// <summary>
        /// Maximum number of packets per batch before writing to the database.
        /// </summary>
        public int BatchSize { get; set; } = 10_000;

        /// <summary>
        /// Maximum wait time in milliseconds before a batch is flushed to the database,
        /// even if BatchSize has not been reached.
        /// </summary>
        public int BatchTimeoutMs { get; set; } = 30;
    }
}