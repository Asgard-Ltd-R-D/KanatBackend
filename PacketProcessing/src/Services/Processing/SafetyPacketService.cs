using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Threading.Channels;
using PacketProcessing.Services.Networking;

namespace PacketProcessing.Services.Processing;

/// <summary>
/// Safety packet service for batch processing safety packets
/// </summary>
public sealed class SafetyPacketService : BasePacketService<SafetyPacketEntity>
{
    public SafetyPacketService(
        ILogger<SafetyPacketService> logger,
        IPacketRepository<SafetyPacketEntity> repository,
        Channel<SafetyPacketEntity> channel,
        SafetyCaptureService captureService,
        IConfiguration configuration)
        : base(logger, repository, channel, captureService, configuration)
    {
    }
}
