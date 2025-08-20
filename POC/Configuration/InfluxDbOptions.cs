namespace PacketProcessing.Configuration;

public class InfluxDbOptions
{
	public const string SectionName = "InfluxDB";
	
	public string Host { get; set; } = "localhost";
	public int Port { get; set; } = 8086;
	public string Username { get; set; } = "admin";
	public string Password { get; set; } = "admin";
	public string Organization { get; set; } = "my-org";
	public string Bucket { get; set; } = "packets";
	public int BatchSize { get; set; } = 1000;
	public int BatchTimeoutMs { get; set; } = 30;
}
