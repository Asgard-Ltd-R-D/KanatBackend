using System.Collections.Concurrent;
using System.Threading.Channels;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using PacketProcessing.DTOs;

namespace PacketProcessing.Telemetry;

/// <summary>
/// Background service that broadcasts telemetry data to connected SignalR clients
/// </summary>
public class TelemetryBroadcaster : BackgroundService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly IHubContext<TelemetryHub> _hubContext;
    private readonly ILogger<TelemetryBroadcaster> _logger;
    private readonly TelemetryBroadcasterOptions _options;
    
    private readonly Channel<bool> _notificationChannel;
    private readonly ChannelWriter<bool> _notificationWriter;
    private readonly ChannelReader<bool> _notificationReader;
    
    private DateTime _lastPushTime = DateTime.MinValue;
    private readonly SemaphoreSlim _pushSemaphore = new(1, 1);
    private bool _hasInitialPush = false;
    private bool _disposed = false;

    public TelemetryBroadcaster(
        IServiceProvider serviceProvider,
        IHubContext<TelemetryHub> hubContext,
        ILogger<TelemetryBroadcaster> logger,
        IOptions<TelemetryBroadcasterOptions> options)
    {
        _serviceProvider = serviceProvider;
        _hubContext = hubContext;
        _logger = logger;
        _options = options.Value;
        
        var channelOptions = new BoundedChannelOptions(100)
        {
            FullMode = BoundedChannelFullMode.DropOldest,
            SingleReader = true,
            SingleWriter = false
        };
        
        _notificationChannel = Channel.CreateBounded<bool>(channelOptions);
        _notificationWriter = _notificationChannel.Writer;
        _notificationReader = _notificationChannel.Reader;
    }

    /// <summary>
    /// Notifies the broadcaster that telemetry data has changed and should be pushed
    /// </summary>
    public void NotifyChange()
    {
        if (!_options.Enabled)
            return;
            
        // Non-blocking notification
        _notificationWriter.TryWrite(true);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_options.Enabled)
        {
            _logger.LogInformation("TelemetryBroadcaster is disabled");
            return;
        }

        _logger.LogInformation("TelemetryBroadcaster started with MaxPushRateHz={MaxPushRateHz}, MinIntervalMs={MinIntervalMs}", 
            _options.MaxPushRateHz, _options.MinIntervalMs);

        // Force an initial telemetry push to show current state
        await PushTelemetryData(stoppingToken);

        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                try
                {
                    // Wait for notification or timeout
                    using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
                    timeoutCts.CancelAfter(TimeSpan.FromMilliseconds(_options.MinIntervalMs));
                    
                    var hasNotification = await _notificationReader.WaitToReadAsync(timeoutCts.Token);
                    
                    if (hasNotification)
                    {
                        // Drain all pending notifications (coalesce)
                        while (_notificationReader.TryRead(out _)) { }
                        
                        await PushTelemetryData(stoppingToken);
                    }
                    // No timeout push - only push when there are actual changes
                }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                {
                    break;
                }
                catch (OperationCanceledException)
                {
                    // Timeout occurred - just continue waiting for changes
                    // No need to push unless there are actual changes
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error in TelemetryBroadcaster main loop");
                    await Task.Delay(1000, stoppingToken); // Brief delay before retry
                }
            }
        }
        finally
        {
            if (!_disposed)
            {
                _notificationWriter.Complete();
            }
        }
    }

    private async Task PushTelemetryData(CancellationToken cancellationToken)
    {
        if (_disposed)
            return;
            
        await _pushSemaphore.WaitAsync(cancellationToken);
        try
        {
            var now = DateTime.UtcNow;
            var timeSinceLastPush = now - _lastPushTime;
            var minInterval = TimeSpan.FromMilliseconds(1000.0 / _options.MaxPushRateHz);
            
            // Rate limiting: don't push more frequently than MaxPushRateHz
            if (timeSinceLastPush < minInterval)
            {
                return;
            }

            // Get telemetry data from service
            using var scope = _serviceProvider.CreateScope();
            var telemetryService = scope.ServiceProvider.GetService<ITelemetryService>();
            
            if (telemetryService == null)
            {
                _logger.LogWarning("ITelemetryService not found, skipping telemetry push");
                return;
            }

            // Check if there are any changes before pushing (skip check for initial push)
            if (!_hasInitialPush)
            {
                _hasInitialPush = true;
            }
            else if (!telemetryService.HasChanges())
            {
                return; // No changes, skip push
            }

            var telemetryData = await telemetryService.SnapshotAsync();
            
            // Push to all connected clients
            await _hubContext.Clients.All.SendAsync("telemetry:update", telemetryData, cancellationToken);
            
            // Mark that we've taken a snapshot
            telemetryService.MarkSnapshotTaken();
            
            _lastPushTime = now;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error pushing telemetry data");
        }
        finally
        {
            _pushSemaphore.Release();
        }
    }

    public override void Dispose()
    {
        if (_disposed)
            return;
            
        _disposed = true;
        
        try
        {
            _notificationWriter.Complete();
        }
        catch (InvalidOperationException)
        {
            // Channel already completed, ignore
        }
        
        _pushSemaphore.Dispose();
        base.Dispose();
    }
}

/// <summary>
/// Configuration options for TelemetryBroadcaster
/// </summary>
public class TelemetryBroadcasterOptions
{
    public bool Enabled { get; set; } = true;
    public double MaxPushRateHz { get; set; } = 10.0;
    public int MinIntervalMs { get; set; } = 100;
}
