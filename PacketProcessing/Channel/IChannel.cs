using Microsoft.Extensions.Hosting;

namespace PacketProcessing.Channel;

public interface IChannel<in T> : IHostedService, IDisposable where T : class
{ 
    int CurrentWorkers { get; }
    int MaxQueueSize { get; }
    int CurrentQueueSize { get; }
    
    ValueTask EnqueueAsync(T packet, CancellationToken ct = default);
    bool TryEnqueue(T packet);
}