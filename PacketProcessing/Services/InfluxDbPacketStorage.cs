using System.Net.Sockets;
using System.Threading.Channels;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using PacketProcessing.Configuration;
using PacketProcessing.Interfaces;
using PacketProcessing.Models;
using QuestDB;
using QuestDB.Senders;

namespace PacketProcessing.Services;

public class InfluxDbPacketStorage : IPacketStorage, IDisposable
{
	private readonly ILogger<InfluxDbPacketStorage> _logger;
	private readonly InfluxDbOptions _options;
	private ISender _sender;
	private readonly SemaphoreSlim _writeLock = new SemaphoreSlim(1, 1);
	private readonly string _connectionString;
	private readonly Channel<PacketData> _packetChannel;
	private readonly CancellationTokenSource _cancellationTokenSource;
	private readonly Task _processingTask;

	public InfluxDbPacketStorage(
		ILogger<InfluxDbPacketStorage> logger,
		IOptions<InfluxDbOptions> options)
	{
		_logger = logger;
		_options = options.Value;

		// Use QuestDB's native client with auto-flush for high performance
		// auto_flush_rows=100: flush every 100 rows
		// auto_flush_interval=1000: flush every 1000ms (1 second)
		_connectionString = $"http::addr={_options.Host}:{_options.Port};username={_options.Username};password={_options.Password};auto_flush_rows={_options.BatchSize};auto_flush_interval={_options.BatchTimeoutMs};";
		_sender = Sender.New(_connectionString);

		// Increase channel capacity significantly to handle burst traffic
		_packetChannel = Channel.CreateBounded<PacketData>(new BoundedChannelOptions(_options.BatchSize * 1000)
		{
			FullMode = BoundedChannelFullMode.Wait
		});

		_cancellationTokenSource = new CancellationTokenSource();
		_processingTask = Task.Run(ProcessPacketsAsync);

		_logger.LogInformation("QuestDB ILP Packet Storage initialized with auto-flush: {BatchSize} rows, {Timeout}ms interval, channel capacity: {Capacity}",
			_options.BatchSize, _options.BatchTimeoutMs, _options.BatchSize * 100);
	}

	public async Task StorePacketAsync(PacketData packet)
	{
		try
		{
			await _packetChannel.Writer.WriteAsync(packet, _cancellationTokenSource.Token);
		}
		catch (Exception ex)
		{
			_logger.LogError(ex, "Error storing packet {Id}", packet.Id);
		}
	}

	public async Task StorePacketsBatchAsync(IEnumerable<PacketData> packets)
	{
		try
		{
			await ProcessBatchAsync([.. packets]);
		}
		catch (Exception ex)
		{
			_logger.LogError(ex, "Error storing batch of {Count} packets", packets.Count());
		}
	}

	public async Task<IEnumerable<PacketData>> GetPacketsAsync(DateTime from, DateTime to, int limit = 1000)
	{
		// Not performance critical; implement later if needed. Return empty for now.
		return await Task.FromResult(Enumerable.Empty<PacketData>());
	}

	public async Task<long> GetPacketCountAsync(DateTime from, DateTime to)
	{
		// Not performance critical; implement later if needed.
		return await Task.FromResult(0L);
	}

	private async Task ProcessPacketsAsync()
	{
		try
		{
			while (!_cancellationTokenSource.Token.IsCancellationRequested)
			{
				var batch = new List<PacketData>();
				var timeout = TimeSpan.FromMilliseconds(_options.BatchTimeoutMs);
				var startTime = DateTime.UtcNow;

				// Collect packets more aggressively
				while (batch.Count < _options.BatchSize && DateTime.UtcNow - startTime < timeout && !_cancellationTokenSource.Token.IsCancellationRequested)
				{
					try
					{
						var readTask = _packetChannel.Reader.ReadAsync(_cancellationTokenSource.Token).AsTask();
						if (await Task.WhenAny(readTask, Task.Delay(5, _cancellationTokenSource.Token)) == readTask)
						{
							batch.Add(await readTask);
						}
						else if (batch.Count > 0)
						{
							break;
						}
					}
					catch (OperationCanceledException)
					{
						break;
					}
				}

				if (batch.Count > 0)
				{
					await ProcessBatchAsync(batch);
				}
			}
		}
		catch (Exception ex)
		{
			_logger.LogError(ex, "Error in packet processing loop");
		}
	}
	private async Task ProcessBatchAsync(List<PacketData> packets)
	{
		if (packets.Count == 0) return;

		// Sort by timestamp (good for QuestDB ingestion)
		packets.Sort((a, b) =>
		{
			var cmp = a.Timestamp.CompareTo(b.Timestamp);
			return cmp != 0 ? cmp : a.Id.CompareTo(b.Id);
		});

		try
		{
			foreach (var packet in packets)
			{
				_sender.Table("packets")
					// Low-cardinality as SYMBOLs
					.Symbol("protocol", packet.Protocol ?? string.Empty)
					.Symbol("device_name", packet.DeviceName ?? string.Empty)
					// High-cardinality as COLUMNS
					.Column("id", packet.Id.ToString())
					.Column("source_ip", packet.SourceIp ?? string.Empty)
					.Column("destination_ip", packet.DestinationIp ?? string.Empty)
					.Column("source_port", packet.SourcePort)
					.Column("destination_port", packet.DestinationPort)
					.Column("length", packet.Length)
					// (payload omitted on purpose for stability; add in slower side-path if needed)
					.At(packet.Timestamp);
			}

			if (packets.Count > 1)
			{
				var firstTime = packets.First().Timestamp;
				var lastTime = packets.Last().Timestamp;
				_logger.LogDebug("QuestDB ILP batch {Count}, range {First} to {Last}",
					packets.Count, firstTime.ToString("HH:mm:ss.ffffff"), lastTime.ToString("HH:mm:ss.ffffff"));
			}

			// Optional: notify last packet elsewhere
			await SendPacketViaWebSocketAsync(packets[^1]);
		}
		catch (Exception ex) when (ex is IOException || ex is SocketException || ex.GetType().Name.Contains("Ingress"))
		{
			_logger.LogWarning(ex, "ILP write failed; recreating sender and retrying batch once...");
			try { _sender?.Dispose(); } catch { /* ignore */ }
			await Task.Delay(250, _cancellationTokenSource.Token);

			// Recreate the sender
			_sender = Sender.New(_connectionString);

			// Retry once
			foreach (var packet in packets)
			{
				_sender.Table("packets")
					.Symbol("protocol", packet.Protocol ?? string.Empty)
					.Symbol("device_name", packet.DeviceName ?? string.Empty)
					.Column("id", packet.Id.ToString())
					.Column("source_ip", packet.SourceIp ?? string.Empty)
					.Column("destination_ip", packet.DestinationIp ?? string.Empty)
					.Column("source_port", packet.SourcePort)
					.Column("destination_port", packet.DestinationPort)
					.Column("length", packet.Length)
					.At(packet.Timestamp);
			}
		}
	}

	private async Task SendPacketViaWebSocketAsync(PacketData packet)
	{
		// TODO: Implement WebSocket broadcasting
		await Task.CompletedTask;
	}

	public void Dispose()
	{
		_cancellationTokenSource.Cancel();
		try { _processingTask?.Wait(TimeSpan.FromSeconds(3)); } catch { }
		_cancellationTokenSource?.Dispose();
		_sender?.Dispose();
		//_writeLock?.Dispose();
	}
}
