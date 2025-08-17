using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using PacketProcessing.Interfaces;
using PacketProcessing.Models;
using PacketProcessing.Configuration;
using Npgsql;
using System.Collections.Generic;
using System.Threading.Channels;
using System.Data;

namespace PacketProcessing.Services;

public class QuestDbPacketStorage : IPacketStorage, IDisposable
{
    private readonly ILogger<QuestDbPacketStorage> _logger;
    private readonly QuestDbOptions _options;
    private readonly string _connectionString;
    private readonly Channel<PacketData> _packetChannel;
    private readonly CancellationTokenSource _cancellationTokenSource;
    private readonly Task _processingTask;
    private readonly List<PacketData> _batchBuffer;
    private readonly object _batchLock = new();
    private readonly Timer _batchTimer;

    public QuestDbPacketStorage(
        ILogger<QuestDbPacketStorage> logger,
        IOptions<QuestDbOptions> options)
    {
        _logger = logger;
        _options = options.Value;
        
        // Initialize connection string with QuestDB-specific parameters
        _connectionString = $"Host={_options.Host};Port={_options.Port};Username={_options.Username};Password={_options.Password};Database={_options.Database};ServerCompatibilityMode=NoTypeLoading;";
        
        // Initialize channel and processing
        _packetChannel = Channel.CreateUnbounded<PacketData>(new UnboundedChannelOptions
        {
            SingleReader = true,
            SingleWriter = false
        });
        
        _cancellationTokenSource = new CancellationTokenSource();
        _batchBuffer = new List<PacketData>(_options.BatchSize);
        
        // Start batch processing timer (30ms as specified)
        _batchTimer = new Timer(ProcessBatch, null, TimeSpan.FromMilliseconds(_options.BatchTimeoutMs), TimeSpan.FromMilliseconds(_options.BatchTimeoutMs));
        
        // Start the processing task
        _processingTask = Task.Run(ProcessPacketsAsync);
        
        // Ensure table exists during initialization
        _ = Task.Run(async () =>
        {
            try
            {
                await EnsureTableExistsAsync();
                _logger.LogInformation("QuestDB table 'packets' created/verified successfully");
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to create/verify QuestDB table during initialization");
            }
        });
        
        _logger.LogInformation("QuestDB Packet Storage initialized with batch size: {BatchSize}, timeout: {Timeout}ms", 
            _options.BatchSize, _options.BatchTimeoutMs);
    }

    public async Task StorePacketAsync(PacketData packet)
    {
        await _packetChannel.Writer.WriteAsync(packet);
    }

    public async Task StorePacketsBatchAsync(IEnumerable<PacketData> packets)
    {
        foreach (var packet in packets)
        {
            await _packetChannel.Writer.WriteAsync(packet);
        }
    }

    public async Task<IEnumerable<PacketData>> GetPacketsAsync(DateTime from, DateTime to, int limit = 1000)
    {
        try
        {
            var query = @"
                SELECT id, timestamp, source_ip, destination_ip, source_port, destination_port, length, protocol, payload, device_name 
                FROM packets 
                WHERE timestamp >= @from AND timestamp <= @to
                ORDER BY timestamp DESC 
                LIMIT @limit";
            
            var packets = new List<PacketData>();
            
            using var connection = new NpgsqlConnection(_connectionString);
            await connection.OpenAsync();
            
            using var command = new NpgsqlCommand(query, connection);
            command.Parameters.AddWithValue("@from", from);
            command.Parameters.AddWithValue("@to", to);
            command.Parameters.AddWithValue("@limit", limit);
            
            using var reader = await command.ExecuteReaderAsync();
            while (await reader.ReadAsync())
            {
                var packet = new PacketData
                {
                    Id = Guid.Parse(reader.GetString("id")),
                    Timestamp = reader.GetDateTime("timestamp"),
                    SourceIp = reader.GetString("source_ip"),
                    DestinationIp = reader.GetString("destination_ip"),
                    SourcePort = reader.GetInt32("source_port"),
                    DestinationPort = reader.GetInt32("destination_port"),
                    Length = reader.GetInt32("length"),
                    Protocol = reader.GetString("protocol"),
                    Payload = reader.IsDBNull("payload") ? Array.Empty<byte>() : Convert.FromBase64String(reader.GetString("payload")),
                    DeviceName = reader.GetString("device_name")
                };
                packets.Add(packet);
            }
            
            return packets;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error retrieving packets from QuestDB");
            return Enumerable.Empty<PacketData>();
        }
    }

    public async Task<long> GetPacketCountAsync(DateTime from, DateTime to)
    {
        try
        {
            var query = @"
                SELECT COUNT(*) as count FROM packets 
                WHERE timestamp >= @from AND timestamp <= @to";
            
            using var connection = new NpgsqlConnection(_connectionString);
            await connection.OpenAsync();
            
            using var command = new NpgsqlCommand(query, connection);
            command.Parameters.AddWithValue("@from", from);
            command.Parameters.AddWithValue("@to", to);
            
            var result = await command.ExecuteScalarAsync();
            return Convert.ToInt64(result);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error counting packets from QuestDB");
            return 0;
        }
    }

    private async Task ProcessPacketsAsync()
    {
        try
        {
            await foreach (var packet in _packetChannel.Reader.ReadAllAsync(_cancellationTokenSource.Token))
            {
                lock (_batchLock)
                {
                    _batchBuffer.Add(packet);
                    
                    if (_batchBuffer.Count >= _options.BatchSize)
                    {
                        _ = Task.Run(() => ProcessBatchInternalAsync(_batchBuffer.ToList()));
                        _batchBuffer.Clear();
                    }
                }
            }
        }
        catch (OperationCanceledException)
        {
            _logger.LogInformation("Packet processing cancelled");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error in packet processing loop");
        }
    }

    private void ProcessBatch(object? state)
    {
        lock (_batchLock)
        {
            if (_batchBuffer.Count > 0)
            {
                var batchToProcess = _batchBuffer.ToList();
                _batchBuffer.Clear();
                _ = Task.Run(() => ProcessBatchInternalAsync(batchToProcess));
            }
        }
    }

    private async Task ProcessBatchInternalAsync(List<PacketData> packets)
    {
        if (packets.Count == 0) return;

        try
        {
            // Create table if it doesn't exist
            await EnsureTableExistsAsync();
            
            // Sort packets by timestamp to ensure chronological order for QuestDB
            packets.Sort((a, b) => a.Timestamp.CompareTo(b.Timestamp));
            
            // Insert packets in batch using parameterized query
            var insertQuery = @"
                INSERT INTO packets (id, timestamp, source_ip, destination_ip, source_port, destination_port, length, protocol, payload, device_name)
                VALUES (@id, @timestamp, @source_ip, @destination_ip, @source_port, @destination_port, @length, @protocol, @payload, @device_name)";
            
            using var connection = new NpgsqlConnection(_connectionString);
            await connection.OpenAsync();
            
            using var transaction = await connection.BeginTransactionAsync();
            try
            {
                using var command = new NpgsqlCommand(insertQuery, connection, transaction);
                
                foreach (var packet in packets)
                {
                    command.Parameters.Clear();
                    command.Parameters.AddWithValue("@id", packet.Id.ToString());
                    command.Parameters.AddWithValue("@timestamp", packet.Timestamp);
                    command.Parameters.AddWithValue("@source_ip", packet.SourceIp);
                    command.Parameters.AddWithValue("@destination_ip", packet.DestinationIp);
                    command.Parameters.AddWithValue("@source_port", packet.SourcePort);
                    command.Parameters.AddWithValue("@destination_port", packet.DestinationPort);
                    command.Parameters.AddWithValue("@length", packet.Length);
                    command.Parameters.AddWithValue("@protocol", packet.Protocol);
                    command.Parameters.AddWithValue("@payload", Convert.ToBase64String(packet.Payload));
                    command.Parameters.AddWithValue("@device_name", packet.DeviceName);
                    
                    await command.ExecuteNonQueryAsync();
                }
                
                await transaction.CommitAsync();
            }
            catch
            {
                await transaction.RollbackAsync();
                throw;
            }
            
            _logger.LogDebug("Successfully stored {Count} packets in batch", packets.Count);
            
            // Send last packet via WebSocket (placeholder for now)
            var lastPacket = packets.Last();
            await SendPacketViaWebSocketAsync(lastPacket);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error processing batch of {Count} packets", packets.Count);
        }
    }

    private async Task EnsureTableExistsAsync()
    {
        try
        {
            // Check if table exists first
            if (await TableExistsAsync())
            {
                _logger.LogDebug("Table 'packets' already exists, skipping creation");
                return;
            }

            _logger.LogInformation("Creating table 'packets' in QuestDB...");
            
            var createTableQuery = @"
                CREATE TABLE packets (
                    id STRING,
                    timestamp TIMESTAMP,
                    source_ip STRING,
                    destination_ip STRING,
                    source_port INT,
                    destination_port INT,
                    length INT,
                    protocol STRING,
                    payload STRING,
                    device_name STRING
                ) timestamp(timestamp)";
            
            using var connection = new NpgsqlConnection(_connectionString);
            await connection.OpenAsync();
            
            using var command = new NpgsqlCommand(createTableQuery, connection);
            await command.ExecuteNonQueryAsync();
            
            _logger.LogInformation("Table 'packets' created successfully in QuestDB");
        }
        catch (Exception ex)
        {
            // If table already exists, that's fine - just log it
            if (ex.Message.Contains("table already exists"))
            {
                _logger.LogDebug("Table 'packets' already exists (expected)");
                return;
            }
            _logger.LogError(ex, "Failed to create table 'packets' in QuestDB");
            throw;
        }
    }

    private async Task<bool> TableExistsAsync()
    {
        try
        {
            using var connection = new NpgsqlConnection(_connectionString);
            await connection.OpenAsync();
            
            var query = @"
                SELECT COUNT(*) FROM packets";
            
            using var command = new NpgsqlCommand(query, connection);
            var result = await command.ExecuteScalarAsync();
            
            return true; // If we can execute this query, table exists
        }
        catch (Exception ex)
        {
            _logger.LogDebug("Table 'packets' does not exist yet");
            return false;
        }
    }

    private async Task SendPacketViaWebSocketAsync(PacketData packet)
    {
        // TODO: Implement WebSocket transmission
        // This is a placeholder for the WebSocket functionality
        _logger.LogDebug("Would send packet {Id} via WebSocket", packet.Id);
        await Task.CompletedTask;
    }

    public void Dispose()
    {
        _cancellationTokenSource.Cancel();
        _batchTimer?.Dispose();
        _cancellationTokenSource?.Dispose();
    }
}
