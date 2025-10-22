using System.Collections.Concurrent;

namespace PacketProcessing.Hubs.ConnectionManager;

/// <summary>
/// Thread-safe implementation of IConnectionManager that maps user IDs to SignalR connection IDs.
/// Uses a concurrent dictionary to ensure thread safety for multiple concurrent connections.
/// </summary>
public class ConnectionManager : IConnectionManager
{
    // maps connectionId → 0 (single connection per client), the is no importance for the value, it is just a placeholder to ensure the key is unique
    private readonly ConcurrentDictionary<string, byte> _map
      = new();

    /// <summary>
    /// Adds a mapping between a user ID and a SignalR connection ID.
    /// If a mapping already exists for the user ID, it will be overwritten.
    /// </summary>
    /// <param name="connectionId">The SignalR connection identifier.</param>
    public void Add(string connectionId)
    {
        _map[connectionId] = 0;
    }

    /// <summary>
    /// Removes a mapping between a user ID and a SignalR connection ID.
    /// </summary>
    /// <param name="connectionId">The SignalR connection identifier.</param>
    public void Remove(string connectionId)
    {
        _map.TryRemove(connectionId, out _);
    }

    /// <summary>
    /// Gets the SignalR connection ID for a specific user ID.
    /// </summary>
    /// <param name="connectionId">The SignalR connection identifier.</param>
    /// <returns>The SignalR connection identifier if found; otherwise, null.</returns>
    public bool? GetConnectionId(string connectionId)
    {
        return _map.TryGetValue(connectionId, out _);
    }

}