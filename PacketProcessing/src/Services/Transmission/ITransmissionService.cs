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
    Task RegisterStreamAsync(StreamRequest request);
    
    /// <summary>
    /// Unregister a stream request
    /// </summary>
    Task UnregisterStreamAsync(StreamRequest request);
    
    /// <summary>
    /// Unregister all stream requests
    /// </summary>
    Task UnregisterAllStreamsAsync();
    
    /// <summary>
    /// Get all registered stream requests
    /// </summary>
    ICollection<StreamRequest> GetRegisteredStreams();
}
