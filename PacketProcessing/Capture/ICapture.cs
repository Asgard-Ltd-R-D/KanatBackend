using Microsoft.Extensions.Hosting;

namespace PacketProcessing.Capture;

public interface ICapture<T> : IHostedService, IDisposable where T : class
{
    string SnifferName { get; }
    string Protocol { get; }
    IReadOnlyList<string> Ips { get; }

    void SetPacketParser(Func<ReadOnlyMemory<byte>, T?> parser);
    void SetPacketHandler(Func<T, Task> handler);
}