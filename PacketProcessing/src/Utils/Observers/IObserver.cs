using PacketProcessing.Entities;

namespace PacketProcessing.Utils.Observers;

/// <summary>
/// Observer interface for packet sampling logic
/// </summary>
/// <typeparam name="T">Type of packet entity to observe</typeparam>
public interface IObserver<in T> where T : BasePacketEntity
{
    /// <summary>
    /// Executes the observer logic on a captured packet
    /// </summary>
    /// <param name="packet">The packet to process</param>
    void Update(T packet);
}
