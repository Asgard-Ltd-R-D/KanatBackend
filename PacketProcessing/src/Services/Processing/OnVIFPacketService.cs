using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Threading.Channels;
using PacketProcessing.Services.Networking;
using PacketProcessing.SignalR;
using PacketProcessing.Utils.Enums;
using QuestDB;
using QuestDB.Senders;
using PacketProcessing.Config;
using Microsoft.AspNetCore.SignalR.Client;
using PacketProcessing.Utils.Observers;
using PacketProcessing.Utils;

namespace PacketProcessing.Services.Processing;

public sealed record SampleOnVifPacket(OnVIFPacketEntity Packet = null!, DateTimeOffset Timestamp = default, CancellationToken CancellationToken = default);

/// <summary>
/// OnVIF packet service for batch processing OnVIF packets
/// </summary>
public sealed class OnVIFPacketService : BasePacketService<OnVIFPacketEntity>
{
    private readonly SignalRClientSession _session;
    private readonly IPacketRepository<OnVIFPacketEntity> _repository;
    private readonly string _questDbConnectionString;
    private readonly OnVIFCaptureService _captureService;

    private IProducer<OnVIFPacketEntity> _packetSamplingProducer = null!;
    private PacketSamplingObserver<OnVIFPacketEntity> _packetSamplingObserver = null!;

    public OnVIFPacketService(
        ILogger<OnVIFPacketService> logger,
        IPacketRepository<OnVIFPacketEntity> repository,
        Channel<OnVIFPacketEntity> channel,
        OnVIFCaptureService captureService,
        IConfiguration configuration,
        IHubClientHost host)
        : base(logger, channel, configuration)
    {
        _session = new SignalRClientSession(host);
        _repository = repository;
        _captureService = captureService;
        
        // Get QuestDB connection string from configuration
        var questDbOptions = configuration.GetSection("QuestDb").Get<QuestDbConfiguration>();
        _questDbConnectionString = questDbOptions?.GetPostgresConnectionString() ?? 
                                  configuration.GetConnectionString("QuestDb") ?? 
                                  throw new InvalidOperationException("QuestDB connection string not found");

        // Setup packet sampling observer
        SetupPacketSamplingObserver();
    }

    #region Data Access Methods

    public override async Task<IEnumerable<OnVIFPacketEntity>> GetAllAsync()
    {
        return await _repository.GetAllFromQuestDbAsync();
    }

    public override async Task<IEnumerable<OnVIFPacketEntity>> GetPaginatedAsync(DateTime startTimestamp, DateTime endTimestamp, OrderBy orderBy = OrderBy.Asc, int page = 1, int pageSize = 1000)
    {
        return await _repository.GetPaginatedFromQuestDbAsync(startTimestamp, endTimestamp, orderBy, page, pageSize);
    }

    public override async Task DeleteAllAsync()
    {
        await _repository.DeleteAllFromQuestDbAsync();
    }

    #endregion

    #region Capture Control Methods

    public async Task StartCaptureAsync()
    {
        await _captureService.StartCaptureAsync();
    }

    public async Task StopCaptureAsync()
    {
        await _captureService.StopCaptureAsync();
    }

    public bool IsCapturing => _captureService.IsCapturing;

    #endregion

    #region Packet Processing Methods

    protected override async Task ProcessPacketBatchAsync(List<OnVIFPacketEntity> batch, int workerId, CancellationToken ct)
    {
        ISender? sender = null;

        try
        {
            // Create ISender for batch processing
            sender = Sender.New(_questDbConnectionString);

            // Write batch to QuestDB
            await _repository.WriteBatchQuestDbAsync(sender, batch, ct); 
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Worker {WorkerId} failed to process batch of {Count} OnVIF packets", 
                workerId, batch.Count);
        }
        finally 
        {
            sender?.Dispose();
        }
    }

    #endregion

    #region Observer Setup Methods

    private void SetupPacketSamplingObserver()
    {
        // Get sampling interval from configuration
        var samplingIntervalMs = _configuration.GetSection("DataPipes:OnVIFCapture:Sampling:IntervalMs").Get<int>();
        if (samplingIntervalMs == 0)
        {
            samplingIntervalMs = Constants.DEFAULT_PACKET_SAMPLE_MS;
        }

        // Create producer for packet sampling
        _packetSamplingProducer = _session.AttachProducer<OnVIFPacketEntity>(
            (hub, packet, ct) => hub.InvokeAsync("SendOnVIFPacketSample", packet, ct));

        // Create packet sampling observer with configured interval
        _packetSamplingObserver = new PacketSamplingObserver<OnVIFPacketEntity>(
            new LoggerFactory().CreateLogger<PacketSamplingObserver<OnVIFPacketEntity>>(),
            _packetSamplingProducer,
            samplingIntervalMs);

        // Subscribe observer to capture service
        _captureService.Subscribe(_packetSamplingObserver);
        
        _logger.LogInformation("OnVIF packet sampling observer subscribed to capture service with {IntervalMs}ms sampling interval", samplingIntervalMs);
    }

    #endregion
}
