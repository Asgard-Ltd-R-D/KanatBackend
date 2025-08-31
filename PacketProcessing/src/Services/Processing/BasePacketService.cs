using PacketProcessing.Entities;
using PacketProcessing.Repositories;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Threading.Channels;
using System.Collections.Concurrent;
using PacketProcessing.Utils.Enums;
using QuestDB;
using PacketProcessing.Config;
using System.Diagnostics.CodeAnalysis;
using Microsoft.AspNetCore.Mvc.TagHelpers;
using QuestDB.Senders;

namespace PacketProcessing.Services.Processing;

/// <summary>
/// Base packet service for batch processing packets with workers and autoscaling
/// </summary>
/// <typeparam name="T">The type of packet entity</typeparam>
public abstract class BasePacketService<T> : IDisposable where T : BasePacketEntity
{
    private readonly ILogger<BasePacketService<T>> _logger;
    private readonly IPacketRepository<T> _repository;
    private readonly Channel<T> _channel;
    private readonly string _questDbConnectionString;
    private readonly int _minWorkers;
    private readonly int _maxWorkers;
    private readonly int _batchSize;
    private readonly TimeSpan _batchTimeout;
    private readonly ConcurrentDictionary<int, Task> _workers;
    private readonly CancellationTokenSource _cancellationTokenSource;
    private int _currentWorkerCount;

    protected BasePacketService(
        ILogger<BasePacketService<T>> logger,
        IPacketRepository<T> repository,
        Channel<T> channel,
        IConfiguration configuration)
    {
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _repository = repository ?? throw new ArgumentNullException(nameof(repository));
        _channel = channel ?? throw new ArgumentNullException(nameof(channel));
        
        // Get QuestDB connection string from configuration
        var questDbOptions = configuration.GetSection("QuestDb").Get<QuestDbConfiguration>();
        _questDbConnectionString = questDbOptions?.GetPostgresConnectionString() ?? 
                                  configuration.GetConnectionString("QuestDb") ?? 
                                  throw new InvalidOperationException("QuestDB connection string not found");
        
        // Get concurrency configuration
        var concurrencySection = configuration.GetSection("Concurrency");
        _minWorkers = concurrencySection.GetValue<int>("MinWorkers", 1);
        _maxWorkers = concurrencySection.GetValue<int>("MaxWorkers", 8);
        _batchSize = concurrencySection.GetValue<int>("BatchSize", 100);
        _batchTimeout = TimeSpan.FromMilliseconds(concurrencySection.GetValue<int>("BatchTimeoutMs", 1000));
        
        _workers = new ConcurrentDictionary<int, Task>();
        _cancellationTokenSource = new CancellationTokenSource();
        _currentWorkerCount = _minWorkers;
        
        _logger.LogInformation("Initialized {ServiceType} with {MinWorkers}-{MaxWorkers} workers, batch size: {BatchSize}, timeout: {BatchTimeout}",
            typeof(T).Name, _minWorkers, _maxWorkers, _batchSize, _batchTimeout);
    }

    /// <summary>
    /// Starts the packet processing service
    /// </summary>
    public async Task StartAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            _logger.LogInformation("Starting {ServiceType} packet processing service", typeof(T).Name);
            
            // Start initial workers
            await StartWorkers(_minWorkers);
            
            // Start the main processing loop
            _ = Task.Run(async () =>
            {
                try
                {
                    while (!cancellationToken.IsCancellationRequested)
                    {
                        await Task.Delay(1000, cancellationToken); // Check every second
                        
                        // Auto-scale based on channel pressure
                        await AutoScaleWorkers();
                    }
                }
                catch (OperationCanceledException) { /* normal on shutdown */ }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error in {ServiceType} packet processing service", typeof(T).Name);
                }
                finally
                {
                    await StopAllWorkers();
                    _logger.LogInformation("Stopped {ServiceType} packet processing service", typeof(T).Name);
                }
            }, cancellationToken);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to start {ServiceType} packet processing service", typeof(T).Name);
            throw;
        }
    }

    /// <summary>
    /// Stops the packet processing service
    /// </summary>
    public async Task StopAsync()
    {
        try
        {
            _logger.LogInformation("Stopping {ServiceType} packet processing service", typeof(T).Name);
            _cancellationTokenSource.Cancel();
            await StopAllWorkers();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error stopping {ServiceType} packet processing service", typeof(T).Name);
        }
    }

    /// <summary>
    /// Starts the specified number of workers
    /// </summary>
    private Task StartWorkers(int count)
    {
        for (int i = 0; i < count && _currentWorkerCount < _maxWorkers; i++)
        {
            var workerId = Interlocked.Increment(ref _currentWorkerCount) - 1;
            var workerTask = Task.Run(() => WorkerLoopAsync(workerId, _cancellationTokenSource.Token));
            
            if (_workers.TryAdd(workerId, workerTask))
            {
                _logger.LogDebug("Started worker {WorkerId} for {ServiceType}", workerId, typeof(T).Name);
            }
        }
        
        return Task.CompletedTask;
    }

    /// <summary>
    /// Auto-scales workers based on channel pressure
    /// </summary>
    private async Task AutoScaleWorkers()
    {
        var channelCount = _channel.Reader.Count;
        var currentWorkers = _workers.Count;
        
        // Scale up if channel is getting full
        if (channelCount > _batchSize * currentWorkers && currentWorkers < _maxWorkers)
        {
            var workersToAdd = Math.Min(2, _maxWorkers - currentWorkers);
            await StartWorkers(workersToAdd);
            _logger.LogInformation("Auto-scaled up {ServiceType} workers by {Count} (channel pressure: {ChannelCount})",
                typeof(T).Name, workersToAdd, channelCount);
        }
        // Scale down if channel is mostly empty
        else if (channelCount < _batchSize && currentWorkers > _minWorkers)
        {
            var workersToRemove = Math.Min(1, currentWorkers - _minWorkers);
            await StopWorkers(workersToRemove);
            _logger.LogInformation("Auto-scaled down {ServiceType} workers by {Count} (channel pressure: {ChannelCount})",
                typeof(T).Name, workersToRemove, channelCount);
        }
    }

    /// <summary>
    /// Stops the specified number of workers
    /// </summary>
    private Task StopWorkers(int count)
    {
        var workersToStop = _workers.Take(count).ToList();
        foreach (var worker in workersToStop)
        {
            if (_workers.TryRemove(worker.Key, out var task))
            {
                _logger.LogDebug("Stopping worker {WorkerId} for {ServiceType}", worker.Key, typeof(T).Name);
            }
        }
        
        return Task.CompletedTask;
    }

    /// <summary>
    /// Stops all workers
    /// </summary>
    private async Task StopAllWorkers()
    {
        _cancellationTokenSource.Cancel();
        
        var tasks = _workers.Values.ToArray();
        if (tasks.Length > 0)
        {
            await Task.WhenAll(tasks);
        }
        
        _workers.Clear();
    }

    /// <summary>
    /// Main batch processing loop for each worker
    /// </summary>
    private async Task WorkerLoopAsync(int workerId, CancellationToken ct)
    {
        _logger.LogDebug("Worker {WorkerId} started processing {ServiceType} batches", workerId, typeof(T).Name);
        
        try
        {
            while (!ct.IsCancellationRequested)
            {
                var batch = new List<T>();
                var batchTimeout = new CancellationTokenSource(_batchTimeout);
                
                // Collect batch
                while (batch.Count < _batchSize && !batchTimeout.Token.IsCancellationRequested)
                {
                    try
                    {
                        // If channel is null, break
                        if (_channel is null) break;

                        // If channel has a packet, add it to the batch
                        else if (_channel.Reader.TryRead(out var packet))
                        {
                            batch.Add(packet);
                        }

                        // If channel has no packet, wait for next packet with timeout
                        else
                        {
                            // Wait for next packet with timeout
                            var readTask = _channel.Reader.ReadAsync(ct).AsTask();
                            var timeoutTask = Task.Delay(_batchTimeout, batchTimeout.Token);
                            var completedTask = await Task.WhenAny(readTask, timeoutTask);
                            if (completedTask == readTask) batch.Add(await readTask);
                            else break;
                        }
                    }
                    catch (OperationCanceledException) when (batchTimeout.Token.IsCancellationRequested)
                    {
                        break; // Batch timeout
                    }
                }
                
                // Process batch if we have packets
                if (batch.Count > 0)
                {
                    await ProcessPacketBatchAsync(batch, workerId, ct);
                }
            }
        }
        catch (OperationCanceledException) { /* normal on shutdown */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Worker {WorkerId} encountered error processing {ServiceType} batches", workerId, typeof(T).Name);
        }
        
        _logger.LogDebug("Worker {WorkerId} stopped processing {ServiceType} batches", workerId, typeof(T).Name);
    }

    /// <summary>
    /// Processes a batch of packets using ISender
    /// </summary>
    private async Task ProcessPacketBatchAsync(List<T> batch, int workerId, CancellationToken ct)
    {
        ISender? sender = null;

        try
        {
            _logger.LogDebug("Worker {WorkerId} processing batch of {Count} {ServiceType} packets", 
                workerId, batch.Count, typeof(T).Name);
            
            // Create ISender for batch processing
            sender = Sender.New(_questDbConnectionString);

            // Write batch to QuestDB
            await _repository.WriteBatchQuestDbAsync(sender, batch, ct); 

            _logger.LogDebug("Worker {WorkerId} successfully processed batch of {Count} {ServiceType} packets", 
                workerId, batch.Count, typeof(T).Name);     
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Worker {WorkerId} failed to process batch of {Count} {ServiceType} packets", 
                workerId, batch.Count, typeof(T).Name);
        }
        finally {
            sender?.Dispose();
            batch?.Clear();
        }
    }

    // Repository access methods
    public async Task<IEnumerable<T>> GetAllAsync() 
        => await _repository.GetAllFromQuestDbAsync();
    public async Task<IEnumerable<T>> GetPaginatedAsync(DateTime startTimestamp, DateTime endTimestamp, OrderBy orderBy = OrderBy.Asc, int page = 1, int pageSize = 1000) 
        => await _repository.GetPaginatedFromQuestDbAsync(startTimestamp, endTimestamp, orderBy, page, pageSize);
    public async Task DeleteAllAsync() 
        => await _repository.DeleteAllFromQuestDbAsync();

    /// <summary>
    /// Disposes the service and cleans up resources
    /// </summary>
    public void Dispose()
    {
        try
        {
            _cancellationTokenSource?.Cancel();
            _cancellationTokenSource?.Dispose();
        }
        catch (Exception ex)
        {
            _logger?.LogError(ex, "Error disposing {ServiceType} packet processing service", typeof(T).Name);
        }
    }
}
