using PacketProcessing.Entities;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Threading.Channels;
using System.Collections.Concurrent;
using PacketProcessing.Utils.Enums;
using static PacketProcessing.Utils.Constants.Constants;

namespace PacketProcessing.Services.Processing;

/// <summary>
/// Base packet service for batch processing packets with workers and autoscaling
/// </summary>
/// <typeparam name="T">The type of packet entity</typeparam>
public abstract class BasePacketService<T> : IDisposable where T : BasePacketEntity
{
    protected readonly ILogger<BasePacketService<T>> _logger;
    protected readonly IConfiguration _configuration;
    protected readonly Channel<T> _channel;

    protected readonly int _minWorkers;
    protected readonly int _maxWorkers;
    protected readonly int _batchSize;

    protected readonly TimeSpan _batchTimeout;
    protected readonly ConcurrentDictionary<int, Task> _workers;
    protected readonly CancellationTokenSource _cancellationTokenSource;
    protected int _currentWorkerCount;

    protected BasePacketService(
        ILogger<BasePacketService<T>> logger,
        Channel<T> channel,
        IConfiguration configuration)
    {
        // Initialize dependencies
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _channel = channel ?? throw new ArgumentNullException(nameof(channel));
        _configuration = configuration;
        
        // Get concurrency configuration
        var concurrencySection = configuration.GetSection("Concurrency");
        _minWorkers = concurrencySection.GetValue<int>("MinWorkers", DEFAULT_MIN_WORKERS);
        _maxWorkers = concurrencySection.GetValue<int>("MaxWorkers", DEFAULT_MAX_WORKERS);
        _batchSize = concurrencySection.GetValue<int>("BatchSize", DEFAULT_BATCH_SIZE);
        _batchTimeout = TimeSpan.FromMilliseconds(concurrencySection.GetValue<int>("BatchTimeoutMs", DEFAULT_BATCH_TIMEOUT_MS));
        
        // Initialize worker pool
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
            
            // Start the main processing loop - optimized for high throughput
            _ = Task.Run(async () =>
            {
                try
                {
                    while (!cancellationToken.IsCancellationRequested)
                    {
                        await Task.Delay(250, cancellationToken); // Check every 250ms for faster response
                        
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
            
            _workers.TryAdd(workerId, workerTask);
        }
        
        return Task.CompletedTask;
    }

    /// <summary>
    /// Auto-scales workers based on channel pressure - optimized for high throughput
    /// </summary>
    private async Task AutoScaleWorkers()
    {
        var channelCount = _channel.Reader.Count;
        var currentWorkers = _workers.Count;
        
        // More aggressive scaling for high throughput scenarios
        var pressureThreshold = _batchSize * currentWorkers;
        var lowPressureThreshold = _batchSize / 2;
        
        // Scale up if channel is getting full (more aggressive for 10k pps)
        if (channelCount > pressureThreshold && currentWorkers < _maxWorkers)
        {
            // Scale up more aggressively for high throughput
            var workersToAdd = Math.Min(4, _maxWorkers - currentWorkers);
            await StartWorkers(workersToAdd);
            _logger.LogInformation("Auto-scaled up {ServiceType} workers by {Count} (channel pressure: {ChannelCount}/{Threshold})",
                typeof(T).Name, workersToAdd, channelCount, pressureThreshold);
        }
        // Scale down if channel is mostly empty (more conservative to avoid thrashing)
        else if (channelCount < lowPressureThreshold && currentWorkers > _minWorkers)
        {
            var workersToRemove = Math.Min(1, currentWorkers - _minWorkers);
            await StopWorkers(workersToRemove);
            _logger.LogInformation("Auto-scaled down {ServiceType} workers by {Count} (channel pressure: {ChannelCount}/{Threshold})",
                typeof(T).Name, workersToRemove, channelCount, lowPressureThreshold);
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
            _workers.TryRemove(worker.Key, out var task);
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
    /// Main batch processing loop for each worker - optimized for high throughput
    /// </summary>
    private async Task WorkerLoopAsync(int workerId, CancellationToken ct)
    {
        // Pre-allocate batch list to avoid allocations in hot path
        var batch = new List<T>(_batchSize);
        var batchTimeoutCts = new CancellationTokenSource();
        
        try
        {
            while (!ct.IsCancellationRequested)
            {
                batch.Clear(); // Reuse the list
                batchTimeoutCts.CancelAfter(_batchTimeout);
                
                // High-performance batch collection
                while (batch.Count < _batchSize && !batchTimeoutCts.Token.IsCancellationRequested)
                {
                    // Fast path: try to read without waiting
                    if (_channel.Reader.TryRead(out var packet))
                    {
                        batch.Add(packet);
                        continue;
                    }
                    
                    // If no packet available, wait briefly for one
                    try
                    {
                        var readTask = _channel.Reader.ReadAsync(ct).AsTask();
                        var timeoutTask = Task.Delay(5, batchTimeoutCts.Token); // Even shorter timeout for maximum responsiveness
                        var completedTask = await Task.WhenAny(readTask, timeoutTask);
                        
                        if (completedTask == readTask)
                        {
                            batch.Add(await readTask);
                        }
                        else
                        {
                            break; // Timeout reached
                        }
                    }
                    catch (OperationCanceledException) when (batchTimeoutCts.Token.IsCancellationRequested)
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
        finally
        {
            batchTimeoutCts?.Dispose();
        }
    }

    /// <summary>
    /// Processes a batch of packets using ISender
    /// Override this method in concrete classes to implement custom batch processing logic
    /// </summary>
    protected abstract Task ProcessPacketBatchAsync(List<T> batch, int workerId, CancellationToken ct);

    // Repository access methods - override in concrete classes
    public abstract Task<IEnumerable<T>> GetAllAsync();
    public abstract Task<IEnumerable<T>> GetPaginatedAsync(DateTime startTimestamp, DateTime endTimestamp, OrderBy orderBy = OrderBy.Asc, int page = 1, int pageSize = 1000);
    public abstract Task DeleteAllAsync();

    /// <summary>
    /// Disposes the service and cleans up resources
    /// </summary>
    public void Dispose()
    {
        try
        {
            _cancellationTokenSource?.Cancel();
            _cancellationTokenSource?.Dispose();
            GC.SuppressFinalize(this);
        }
        catch (Exception ex)
        {
            _logger?.LogError(ex, "Error disposing {ServiceType} packet processing service", typeof(T).Name);
        }
    }
}
