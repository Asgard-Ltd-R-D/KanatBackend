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
    Task DeregisterStreamAsync(StreamRequestDto request);

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
}
