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
    // Timer removed - using new backpressure-controlled approach
    private readonly SemaphoreSlim _semaphore = new SemaphoreSlim(1, 1);

    public QuestDbPacketStorage(
        ILogger<QuestDbPacketStorage> logger,
        IOptions<QuestDbOptions> options)
    {
        _logger = logger;
        _options = options.Value;
        
        // Initialize connection string with QuestDB-specific parameters
        _connectionString = $"Host={_options.Host};Port={_options.Port};Username={_options.Username};Password={_options.Password};Database={_options.Database};ServerCompatibilityMode=NoTypeLoading;";
        
        // Initialize channel with bounded capacity for backpressure control
        _packetChannel = Channel.CreateBounded<PacketData>(new BoundedChannelOptions(_options.BatchSize * 10)
        {
            SingleReader = true,
            SingleWriter = false,
            FullMode = BoundedChannelFullMode.Wait
        });
        
        _cancellationTokenSource = new CancellationTokenSource();
        _batchBuffer = new List<PacketData>(_options.BatchSize);
        
        // No need for timer-based processing with new approach
        // _batchTimer = new Timer(ProcessBatch, null, TimeSpan.FromMilliseconds(_options.BatchTimeoutMs), TimeSpan.FromMilliseconds(_options.BatchTimeoutMs));
        
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
        try
        {
            // Wait for space in the channel (backpressure control)
            await _packetChannel.Writer.WaitToWriteAsync();
            await _packetChannel.Writer.WriteAsync(packet);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to store packet {Id}, channel may be full", packet.Id);
            // Optionally implement retry logic here
        }
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
            while (!_cancellationTokenSource.Token.IsCancellationRequested)
            {
                // Process packets in batches with backpressure control
                var batch = new List<PacketData>();
                
                // Collect packets up to batch size or timeout
                var timeout = TimeSpan.FromMilliseconds(_options.BatchTimeoutMs);
                var startTime = DateTime.UtcNow;
                
                while (batch.Count < _options.BatchSize && 
                       DateTime.UtcNow - startTime < timeout &&
                       !_cancellationTokenSource.Token.IsCancellationRequested)
                {
                    try
                    {
                        // Try to read a packet with a short timeout
                        var readTask = _packetChannel.Reader.ReadAsync(_cancellationTokenSource.Token).AsTask();
                        if (await Task.WhenAny(readTask, Task.Delay(10, _cancellationTokenSource.Token)) == readTask)
                        {
                            var packet = await readTask;
                            batch.Add(packet);
                        }
                        else
                        {
                            // No packet available, break if we have some packets
                            if (batch.Count > 0) break;
                        }
                    }
                    catch (OperationCanceledException)
                    {
                        break;
                    }
                }
                
                // Process the batch if we have packets
                if (batch.Count > 0)
                {
                    await ProcessBatchInternalAsync(batch);
                }
                else
                {
                    // Small delay to prevent busy waiting
                    await Task.Delay(1, _cancellationTokenSource.Token);
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

    // Old timer-based processing removed - using new backpressure-controlled approach

    private async Task ProcessBatchInternalAsync(List<PacketData> packets)
    {
        if (packets.Count == 0) return;

        // Use semaphore to ensure only one database operation at a time
        await _semaphore.WaitAsync();
        try
        {
            // Create table if it doesn't exist
            await EnsureTableExistsAsync();
            
            // Use QuestDB's SYSDATE() function to ensure proper timestamp ordering
            // This bypasses the client-side timestamp ordering issues
            var insertQuery = @"
                INSERT INTO packets (id, timestamp, source_ip, destination_ip, source_port, destination_port, length, protocol, payload, device_name)
                VALUES (@id, SYSDATE(), @source_ip, @destination_ip, @source_port, @destination_port, @length, @protocol, @payload, @device_name)";
            
            // Log batch info for debugging
            if (packets.Count > 1)
            {
                _logger.LogDebug("Processing batch of {Count} packets with QuestDB SYSDATE()", packets.Count);
            }
            
            // Note: insertQuery is now defined above with SYSDATE()
            
            using var connection = new NpgsqlConnection(_connectionString);
            await connection.OpenAsync();
            
            // Use a longer command timeout for QuestDB
            // Note: CommandTimeout is set on the command, not the connection
            
            using var transaction = await connection.BeginTransactionAsync();
            try
            {
                using var command = new NpgsqlCommand(insertQuery, connection, transaction);
                command.CommandTimeout = 60; // Set timeout for QuestDB operations
                
                foreach (var packet in packets)
                {
                    command.Parameters.Clear();
                    command.Parameters.AddWithValue("@id", packet.Id.ToString());
                    // Note: timestamp is now handled by SYSDATE() in the query
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
            catch (Exception ex)
            {
                try
                {
                    if (transaction.Connection != null && transaction.Connection.State == System.Data.ConnectionState.Open)
                    {
                        await transaction.RollbackAsync();
                    }
                }
                catch (Exception rollbackEx)
                {
                    _logger.LogWarning(rollbackEx, "Failed to rollback transaction");
                }
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
        finally
        {
            _semaphore.Release();
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
        _cancellationTokenSource?.Dispose();
    }
}
