using Repository.Interfaces;

namespace PacketProcessing.Capture;

public abstract class BaseCaptureService<T> : BackgroundService where T : class
{
    private readonly ILogger<BaseCaptureService<T>> _logger;
    private readonly IILPRepository _ilpRepository;
    private readonly IOptions<ApplicationOptions.SnifferDefinition> _snifferDefinition;
    private readonly ConcurrentDictionary<string, LibPcapLiveDevice> _activeDevices;
    protected int _currentWorkers = 0;
    protected int _maxQueueSize = 1000;
    protected int _currentQueueSize = 0;

    public BaseCaptureService(
        ILogger<BaseCaptureService<T>> logger,
        IOptions<ApplicationOptions.SnifferDefinition> snifferDefinition,
        ConcurrentDictionary<string, LibPcapLiveDevice> activeDevices)
    {
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            await Task.Delay(1000, stoppingToken);
        }
    }

    public abstract void StartCapture();
    public abstract void StopCapture();
    public abstract T ParsePacket(Packet packet);
    public abstract void HandleBatch(ISender sender, IReadOnlyList<T> batch, CancellationToken ct = default);

}