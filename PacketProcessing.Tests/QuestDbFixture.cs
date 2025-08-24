using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using PacketProcessing.Database;
using PacketProcessing.Entities;
using PacketProcessing.Repositories;
using PacketProcessing.Repositories.EfRepository;
using PacketProcessing.Repositories.InfluxRepository;
using QuestDB;
using QuestDB.Senders;

namespace PacketProcessing.Tests;

public class QuestDbFixture : IAsyncLifetime
{
    private readonly string _pgConn =
        Environment.GetEnvironmentVariable("QDB_PG")
        ?? "Host=localhost;Port=8812;Username=quest;Password=quest;Database=qdb;Pooling=false";

    private readonly string _ilpEndpoint =
        Environment.GetEnvironmentVariable("QDB_ILP") 
        ?? "http::addr=localhost:9000;username=quest;password=quest" +
           "auto_flush_rows=100;auto_flush_interval=30";
    
    public IQuestDbClient _Qdb { get; private set; } = null!;
    public ISender _Sender { get; private set; } = null!;
    
    public async Task InitializeAsync()
    {
        // Raw PG wire client
        _Qdb = new QuestDbClient(_pgConn);
        await _Qdb.OpenAsync();

        // Ensure schema for all entities (id/timestamp + concrete cols)
        await QuestDbSchemaBootstrapper.EnsureAllPacketTablesAsync(_Qdb);

        // ILP sender for writes
        _Sender = Sender.New(_ilpEndpoint);

        // Clean tables so tests start from a known state
        await TruncateAllAsync();
    }
    
    public async Task DisposeAsync()
    {
        try
        {
            _Sender?.Dispose();
        }
        catch { /* ignore */ }

        await _Qdb.DisposeAsync();
    }

    public async Task<long> CountAsync(string table)
        => await _Qdb.ExecuteScalarAsync<long>($"select count(*) from \"{table}\"");
    
    public ISender CreateSender()
        => Sender.New(_ilpEndpoint);

    private async Task TruncateAllAsync()
    {
        // list known packet tables (add more if you add entities)
        var tables = new[] { "motion_packets", "onvif_packets", "safety_packets" };
        foreach (var t in tables)
        {
            await _Qdb.ExecuteAsync($"truncate table \"{t}\"");
        }
    }
    
    public IRepository<T> CreateRepository<T>() where T : BasePacketEntity
    {
        var influx = new InfluxRepository<T>(NullLogger<InfluxRepository<T>>.Instance);
        var ef     = new EfRepository<T>(_Qdb, NullLogger<EfRepository<T>>.Instance);
        return new Repository<T>(influx, ef, NullLogger<Repository<T>>.Instance);
    }
}