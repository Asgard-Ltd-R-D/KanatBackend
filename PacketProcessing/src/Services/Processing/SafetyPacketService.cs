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

public sealed record SampleSafetyPacket(SafetyPacketEntity Packet = null!, DateTimeOffset Timestamp = default, CancellationToken CancellationToken = default);

/// <summary>
/// Safety packet service for batch processing safety packets
/// </summary>
public sealed class SafetyPacketService : BasePacketService<SafetyPacketEntity>
{
    private readonly SignalRClientSession _session;
    private readonly IPacketRepository<SafetyPacketEntity> _repository;
    private readonly string _questDbConnectionString;
    private readonly SafetyCaptureService _captureService;

    private IProducer<SafetyPacketEntity> _packetSamplingProducer = null!;
    private PacketSamplingObserver<SafetyPacketEntity> _packetSamplingObserver = null!;

    public SafetyPacketService(
        ILogger<SafetyPacketService> logger,
        IPacketRepository<SafetyPacketEntity> repository,
        Channel<SafetyPacketEntity> channel,
        SafetyCaptureService captureService,
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

    public override async Task<IEnumerable<SafetyPacketEntity>> GetAllAsync()
    {
        return await _repository.GetAllFromQuestDbAsync();
    }

    public override async Task<IEnumerable<SafetyPacketEntity>> GetPaginatedAsync(DateTime startTimestamp, DateTime endTimestamp, OrderBy orderBy = OrderBy.Asc, int page = 1, int pageSize = 1000)
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

    protected override async Task ProcessPacketBatchAsync(List<SafetyPacketEntity> batch, int workerId, CancellationToken ct)
    {
        ISender? sender = null;

        try
        {
            _logger.LogDebug("Worker {WorkerId} processing batch of {Count} Safety packets", 
                workerId, batch.Count);
            
            // Create ISender for batch processing
            sender = Sender.New(_questDbConnectionString);

            // Write batch to QuestDB
            await _repository.WriteBatchQuestDbAsync(sender, batch, ct); 

            _logger.LogDebug("Worker {WorkerId} successfully processed batch of {Count} Safety packets", 
                workerId, batch.Count);     
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Worker {WorkerId} failed to process batch of {Count} Safety packets", 
                workerId, batch.Count);
        }
        finally 
        {
            sender?.Dispose();
            batch?.Clear();
        }
    }

    #endregion

    #region Observer Setup Methods

    private void SetupPacketSamplingObserver()
    {
        // Get sampling interval from configuration
        var samplingIntervalMs = _configuration.GetSection("DataPipes:SafetyCapture:Sampling:IntervalMs").Get<int>();
        if (samplingIntervalMs == 0)
        {
            samplingIntervalMs = Constants.DEFAULT_PACKET_SAMPLE_MS;
        }

        // Create producer for packet sampling
        _packetSamplingProducer = _session.AttachProducer<SafetyPacketEntity>(
            (hub, packet, ct) => hub.InvokeAsync("SendSafetyPacketSample", packet, ct));

        // Create packet sampling observer with configured interval
        _packetSamplingObserver = new PacketSamplingObserver<SafetyPacketEntity>(
            new LoggerFactory().CreateLogger<PacketSamplingObserver<SafetyPacketEntity>>(),
            _packetSamplingProducer,
            samplingIntervalMs);

        // Subscribe observer to capture service
        _captureService.Subscribe(_packetSamplingObserver);
        
        _logger.LogInformation("Safety packet sampling observer subscribed to capture service with {IntervalMs}ms sampling interval", samplingIntervalMs);
    }

    #endregion
}
