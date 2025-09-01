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
using PacketProcessing.Utils;

namespace PacketProcessing.Services.Processing;

public sealed record SampleMotionPacket(MotionPacketEntity Packet = null!, DateTimeOffset Timestamp = default, CancellationToken CancellationToken = default);

/// <summary>
/// Motion packet service for batch processing motion packets
/// </summary>
public sealed class MotionPacketService : BasePacketService<MotionPacketEntity>
{
    private readonly SignalRClientSession _session;
    private readonly IPacketRepository<MotionPacketEntity> _repository;
    private readonly string _questDbConnectionString;

    private MotionPacketEntity _lastPacket = null!;
    private IProducer<SampleMotionPacket> _packetSampleProducer = null!;

    public MotionPacketService(
        ILogger<MotionPacketService> logger,
        IPacketRepository<MotionPacketEntity> repository,
        Channel<MotionPacketEntity> channel,
        MotionCaptureService captureService,
        IConfiguration configuration,
        IHubClientHost host)
        : base(logger, channel, captureService, configuration)
    {
        _session = new SignalRClientSession(host);
        _repository = repository;
        
        // Get QuestDB connection string from configuration
        var questDbOptions = configuration.GetSection("QuestDb").Get<QuestDbConfiguration>();
        _questDbConnectionString = questDbOptions?.GetPostgresConnectionString() ?? 
                                  configuration.GetConnectionString("QuestDb") ?? 
                                  throw new InvalidOperationException("QuestDB connection string not found");
        
        // Mount producer
        MountProducer();
    }

    protected override async Task ProcessPacketBatchAsync(List<MotionPacketEntity> batch, int workerId, CancellationToken ct)
    {
        ISender? sender = null;

        try
        {
            _logger.LogDebug("Worker {WorkerId} processing batch of {Count} Motion packets", 
                workerId, batch.Count);
            
            // Create ISender for batch processing
            sender = Sender.New(_questDbConnectionString);

            // Write batch to QuestDB
            await _repository.WriteBatchQuestDbAsync(sender, batch, ct); 

            // Send sample packet to SignalR
            if (_lastPacket == null || _lastPacket.Timestamp + TimeSpan.FromMilliseconds(Constants.DEFAULT_PACKET_SAMPLE_MS) < batch.Last().Timestamp)
            {
                _lastPacket = batch.Last();
                await _packetSampleProducer.ProduceAsync(new SampleMotionPacket(_lastPacket, DateTimeOffset.UtcNow), ct);
            }

            _logger.LogDebug("Worker {WorkerId} successfully processed batch of {Count} Motion packets", 
                workerId, batch.Count);     
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Worker {WorkerId} failed to process batch of {Count} Motion packets", 
                workerId, batch.Count);
        }
        finally 
        {
            sender?.Dispose();
            batch?.Clear();
        }
    }

    public override async Task<IEnumerable<MotionPacketEntity>> GetAllAsync()
    {
        return await _repository.GetAllFromQuestDbAsync();
    }

    public override async Task<IEnumerable<MotionPacketEntity>> GetPaginatedAsync(DateTime startTimestamp, DateTime endTimestamp, OrderBy orderBy = OrderBy.Asc, int page = 1, int pageSize = 1000)
    {
        return await _repository.GetPaginatedFromQuestDbAsync(startTimestamp, endTimestamp, orderBy, page, pageSize);
    }

    public override async Task DeleteAllAsync()
    {
        await _repository.DeleteAllFromQuestDbAsync();
    }

    private void MountProducer() 
    {
        _packetSampleProducer = _session.AttachProducer<SampleMotionPacket>(
            (hub, m, ct) => hub.InvokeAsync("SendSampleMotionPacket", m.Packet, m.Timestamp, ct));
    }
}
