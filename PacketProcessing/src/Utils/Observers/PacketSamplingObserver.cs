using Microsoft.Extensions.Logging;
using PacketProcessing.Entities;
using PacketProcessing.SignalR;
using PacketProcessing.Utils;

namespace PacketProcessing.Utils.Observers;

/// <summary>
/// Concrete observer that implements packet sampling logic
/// </summary>
/// <typeparam name="T">Type of packet entity to observe</typeparam>
public class PacketSamplingObserver<T> : IObserver<T> where T : BasePacketEntity
{
    private readonly ILogger<PacketSamplingObserver<T>> _logger;
    private readonly IProducer<T> _signalRProducer;
    private readonly object _samplingLock = new();
    
    private DateTime _lastPacketTimestamp = DateTime.MinValue;
    private int _sampleIntervalMs;

    public PacketSamplingObserver(
        ILogger<PacketSamplingObserver<T>> logger,
        IProducer<T> signalRProducer,
        int sampleIntervalMs)
    {
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _signalRProducer = signalRProducer ?? throw new ArgumentNullException(nameof(signalRProducer));
        _sampleIntervalMs = sampleIntervalMs;
    }

    /// <summary>
    /// Executes the packet sampling logic when a packet is captured
    /// </summary>
    /// <param name="packet">The packet to process</param>
    public void Update(T packet)
    {
        if (packet == null)
        {
            _logger.LogWarning("Received null packet for observation");
            return;
        }

        lock (_samplingLock)
        {
            var currentTime = packet.Timestamp;
            var timeSinceLastPacket = currentTime - _lastPacketTimestamp;

            // Check if enough time has passed since the last packet
            if (_lastPacketTimestamp == DateTime.MinValue || 
                timeSinceLastPacket.TotalMilliseconds >= _sampleIntervalMs)
            {
                _lastPacketTimestamp = currentTime;
                
                // Send packet as sample via SignalR (fire and forget)
                _ = Task.Run(async () =>
                {
                    try
                    {
                        await _signalRProducer.ProduceAsync(packet);
                        _logger.LogDebug("Sent packet sample via SignalR: {PacketId}, Type: {PacketType}", 
                            packet.Id, typeof(T).Name);
                    }
                    catch (Exception ex)
                    {
                        _logger.LogError(ex, "Failed to send packet sample via SignalR: {PacketId}", packet.Id);
                    }
                });
            }
        }
    }
}
