using PacketProcessing.Entities;

namespace PacketProcessing.Utils.Observers;

/// <summary>
/// Observable interface for capture services
/// </summary>
/// <typeparam name="T">Type of packet entity being captured</typeparam>
public interface IObservable<T> where T : BasePacketEntity
{
    /// <summary>
    /// Subscribes an observer to receive packet updates
    /// </summary>
    /// <param name="observer">The observer to subscribe</param>
    void Subscribe(IObserver<T> observer);
    
    /// <summary>
    /// Unsubscribes an observer from receiving packet updates
    /// </summary>
    /// <param name="observer">The observer to unsubscribe</param>
    void Unsubscribe(IObserver<T> observer);
    
    /// <summary>
    /// Notifies all subscribed observers with a captured packet
    /// </summary>
    /// <param name="packet">The packet to notify observers about</param>
    void NotifyObservers(T packet);
}
