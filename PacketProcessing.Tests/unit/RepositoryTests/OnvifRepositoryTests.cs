using PacketProcessing.Entities;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Tests.unit.RepositoryTests;

[Collection(nameof(RepositoryTestsCollection))]
public class OnvifRepositoryTests
{
    private readonly QuestDbFixture _fx;
    private const string Table = "onvif_packets";

    public OnvifRepositoryTests(QuestDbFixture fx) => _fx = fx;

    [Fact]
    public async Task Schema_Table_Exists()
    {
        var names = await _fx._Qdb.QueryAsync(
            $"select table_name from tables() where table_name = '{Table}'",
            r => r.GetString(0));

        names.Should().ContainSingle().Which.Should().Be(Table);
    }

    [Fact]
    public async Task Write_Single_Then_Read_Back()
    {
        await _fx._Qdb.ExecuteAsync($"truncate table \"{Table}\"");
        var repo = _fx.CreateRepository<OnVIFPacketEntity>();

        var now = DateTime.UtcNow;
        var e = new OnVIFPacketEntity
        {
            Type = true,
            Description = "zoom-in",
            Zoom = 2.25f,
            Measurement = 42.5f,
            Timestamp = now
        };

        await repo.WriteAsync(_fx._Sender, e);

        var all = (await repo.GetAllPacketsAsync()).ToList();
        all.Should().HaveCount(1);
        var x = all[0];
        x.Description.Should().Be("zoom-in");
        x.Zoom.Should().BeApproximately(2.25f, 1e-4f);
        x.Measurement.Should().BeApproximately(42.5f, 1e-4f);
        x.Type.Should().BeTrue();
    }

    [Fact]
    public async Task Write_Batch_Then_Read_Paged()
    {
        await _fx._Qdb.ExecuteAsync($"truncate table \"{Table}\"");
        var repo = _fx.CreateRepository<OnVIFPacketEntity>();

        var now = DateTime.UtcNow;
        var batch = Enumerable.Range(0, 10)
            .Select(i => new OnVIFPacketEntity
            {
                Type = i % 2 == 1,
                Description = $"desc{i:D2}",
                Zoom = i % 3 == 0 ? null : (float?)(i * 0.1f),
                Measurement = i * 1.5f,
                Timestamp = now.AddMilliseconds(i)
            })
            .ToList();

        await repo.WriteBatchAsync(_fx._Sender, batch);

        var page2 = (await repo.GetPaginatedPacketsBetweenTimestampsAsync(
            now.AddMinutes(-1), now.AddMinutes(1), OrderBy.Asc, page: 2, pageSize: 4)).ToList();

        page2.Should().HaveCount(4);
        page2.First().Description.Should().Be("desc04");
        page2.Last().Description.Should().Be("desc07");
    }

    [Fact]
    public async Task DeleteAll_Truncates_Table()
    {
        await _fx._Qdb.ExecuteAsync($"truncate table \"{Table}\"");
        var repo = _fx.CreateRepository<OnVIFPacketEntity>();

        await repo.WriteAsync(_fx._Sender, new OnVIFPacketEntity
        {
            Type = false,
            Description = "to-delete",
            Zoom = null,
            Measurement = 9.9f,
            Timestamp = DateTime.UtcNow
        });

        (await _fx.CountAsync(Table)).Should().Be(1);

        await repo.DeleteAllPacketsAsync();

        (await _fx.CountAsync(Table)).Should().Be(0);
    }
}
