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

/// <summary>
/// OnVIF packet service for batch processing OnVIF packets
/// </summary>
public sealed class OnVIFPacketService : BasePacketService<OnVIFPacketEntity>
{
    private readonly SignalRClientSession _session;
    private readonly IPacketRepository<OnVIFPacketEntity> _repository;
    private readonly string _questDbConnectionString;

    public OnVIFPacketService(
        ILogger<OnVIFPacketService> logger,
        IPacketRepository<OnVIFPacketEntity> repository,
        Channel<OnVIFPacketEntity> channel,
        OnVIFCaptureService captureService,
        IConfiguration configuration,
        IHubClientHost host)
        : base(logger, repository, channel, captureService, configuration)
    {
        _session = new SignalRClientSession(host);
        _repository = repository;
        
        // Get QuestDB connection string from configuration
        var questDbOptions = configuration.GetSection("QuestDb").Get<QuestDbConfiguration>();
        _questDbConnectionString = questDbOptions?.GetPostgresConnectionString() ?? 
                                  configuration.GetConnectionString("QuestDb") ?? 
                                  throw new InvalidOperationException("QuestDB connection string not found");
    }

    protected override async Task ProcessPacketBatchAsync(List<OnVIFPacketEntity> batch, int workerId, CancellationToken ct)
    {
        ISender? sender = null;

        try
        {
            _logger.LogDebug("Worker {WorkerId} processing batch of {Count} OnVIF packets", 
                workerId, batch.Count);
            
            // Create ISender for batch processing
            sender = Sender.New(_questDbConnectionString);

            // Write batch to QuestDB
            await _repository.WriteBatchQuestDbAsync(sender, batch, ct); 

            _logger.LogDebug("Worker {WorkerId} successfully processed batch of {Count} OnVIF packets", 
                workerId, batch.Count);     
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Worker {WorkerId} failed to process batch of {Count} OnVIF packets", 
                workerId, batch.Count);
        }
        finally 
        {
            sender?.Dispose();
            batch?.Clear();
        }
    }

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
}
