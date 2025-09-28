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

namespace PacketProcessing.Services.Processing;

public sealed record SampleOnVifPacket(OnVIFPacketEntity Packet = null!, DateTimeOffset Timestamp = default, CancellationToken CancellationToken = default);

/// <summary>
/// OnVIF packet service for batch processing OnVIF packets
/// </summary>
public sealed class OnVIFPacketService : BasePacketService<OnVIFPacketEntity>
{
    private readonly HubClient _hubClient;
    private readonly IPacketRepository<OnVIFPacketEntity> _repository;
    private readonly string _questDbConnectionString;
    private readonly CaptureService<OnVIFPacketEntity> _captureService;


    public OnVIFPacketService(
        ILogger<OnVIFPacketService> logger,
        IPacketRepository<OnVIFPacketEntity> repository,
        Channel<OnVIFPacketEntity> channel,
        CaptureService<OnVIFPacketEntity> captureService,
        IConfiguration configuration,
        HubClient hubClient)
        : base(logger, channel, configuration)
    {
        _repository = repository;
        _captureService = captureService;
        _hubClient = hubClient;
        
        // Get QuestDB connection string from configuration
        var questDbOptions = configuration.GetSection("QuestDb").Get<QuestDbConfiguration>();
        _questDbConnectionString = questDbOptions?.GetPostgresConnectionString() ?? 
                                  configuration.GetConnectionString("QuestDb") ?? 
                                  throw new InvalidOperationException("QuestDB connection string not found");
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

    #endregion
}
