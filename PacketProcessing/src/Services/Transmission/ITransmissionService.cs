using PacketProcessing.DTOs.Stream;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Services.Transmission;

/// <summary>
/// Transmission service that observes packet streams and transmits them to SignalR clients
/// Supports both real-time and playback modes
/// </summary>
public interface ITransmissionService : IObserver<BasePacketEntity>
{
    /// <summary>
    /// Register a stream request for transmission
    /// </summary>
    Task RegisterStreamAsync(StreamRequestDto request, string connectionId);
    
    /// <summary>
    /// Deregister a stream request
    /// </summary>
    Task DeregisterStreamAsync(string subscriptionKey);

    /// <summary>
    /// Unregister a stream request by connection ID
    /// </summary>
    Task DeregisterFromAllStreamsAsync(string connectionId);

    /// <summary>
    /// Unregister all stream requests
    /// </summary>
    Task UnregisterAllStreamsAsync();

    /// <summary>
    /// Get all registered streams for a specific connection ID
    /// </summary>
    ICollection<string> GetRegisteredStreamKeys(string connectionId);

    /// <summary>
    /// Set the interval for a specific subscription key
    /// </summary>
    /// <param name="subscriptionKey">The stream subscription key</param>
    /// <param name="intervalMs">Interval in milliseconds (0 disables sampling)</param>
    /// <param name="connectionId">The connection ID</param>
    /// <returns>A task representing the asynchronous operation</returns>
    /// <exception cref="ArgumentNullException">Thrown when request or connectionId is null</exception>
    /// <exception cref="ArgumentException">Thrown when interval is invalid</exception>
    Task SetTimeIntervalAsync(string subscriptionKey, int intervalMs, string connectionId);
}
