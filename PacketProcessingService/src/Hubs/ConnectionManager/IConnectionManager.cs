// IUserConnectionManager.cs

namespace PacketProcessing.Hubs.ConnectionManager;

/// <summary>
/// Interface for managing user connection mappings between user IDs and SignalR connection IDs.
/// </summary>
public interface IConnectionManager
{
    /// <summary>
    /// Adds a mapping between a user ID and a SignalR connection ID.
    /// </summary>
    /// <param name="connectionId">The SignalR connection identifier.</param>
    void Add(string connectionId);

    /// <summary>
    /// Removes a mapping between a user ID and a SignalR connection ID.
    /// </summary>
    /// <param name="connectionId">The SignalR connection identifier.</param>
    void Remove(string connectionId);

    /// <summary>
    /// Gets the SignalR connection ID for a specific user ID.
    /// </summary>
    /// <param name="connectionId">The SignalR connection identifier.</param>
    /// <returns>The SignalR connection identifier if found; otherwise, null.</returns>
    bool? GetConnectionId(string connectionId);
}