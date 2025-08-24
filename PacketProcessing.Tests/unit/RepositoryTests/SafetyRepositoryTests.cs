using PacketProcessing.Entities;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Tests.unit.RepositoryTests;

[Collection(nameof(RepositoryTestsCollection))]
public class SafetyRepositoryTests
{
    private readonly QuestDbFixture _fx;
    private const string Table = "safety_packets";

    public SafetyRepositoryTests(QuestDbFixture fx) => _fx = fx;

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
        var repo = _fx.CreateRepository<SafetyPacketEntity>();

        var now = DateTime.UtcNow;
        var e = new SafetyPacketEntity
        {
            Type = true,
            OpCode = "SAFE",
            OpCodeDescription = "green",
            State = "GREEN",
            Timestamp = now
        };

        await repo.WriteAsync(_fx._Sender, e);

        var all = (await repo.GetAllPacketsAsync()).ToList();
        all.Should().HaveCount(1);
        var x = all[0];
        x.OpCode.Should().Be("SAFE");
        x.State.Should().Be("GREEN");
        x.Type.Should().BeTrue();
    }

    [Fact]
    public async Task Write_Batch_Then_Read_Paged()
    {
        await _fx._Qdb.ExecuteAsync($"truncate table \"{Table}\"");
        var repo = _fx.CreateRepository<SafetyPacketEntity>();

        var now = DateTime.UtcNow;
        var batch = Enumerable.Range(0, 8)
            .Select(i => new SafetyPacketEntity
            {
                Type = i % 2 == 0,
                OpCode = $"OC{i}",
                OpCodeDescription = "batch",
                State = (i % 3 == 0) ? "GREEN" : "YELLOW",
                Timestamp = now.AddMilliseconds(i)
            })
            .ToList();

        await repo.WriteBatchAsync(_fx._Sender, batch);

        var page1 = (await repo.GetPaginatedPacketsBetweenTimestampsAsync(
            now.AddMinutes(-1), now.AddMinutes(1), OrderBy.Asc, page: 1, pageSize: 5)).ToList();
        page1.Should().HaveCount(5);
        page1.First().OpCode.Should().Be("OC0");

        var page2 = (await repo.GetPaginatedPacketsBetweenTimestampsAsync(
            now.AddMinutes(-1), now.AddMinutes(1), OrderBy.Asc, page: 2, pageSize: 5)).ToList();
        page2.Should().HaveCount(3);
        page2.Last().OpCode.Should().Be("OC7");
    }

    [Fact]
    public async Task DeleteAll_Truncates_Table()
    {
        await _fx._Qdb.ExecuteAsync($"truncate table \"{Table}\"");
        var repo = _fx.CreateRepository<SafetyPacketEntity>();

        await repo.WriteAsync(_fx._Sender, new SafetyPacketEntity
        {
            Type = false,
            OpCode = "DEL",
            OpCodeDescription = "to-delete",
            State = "RED",
            Timestamp = DateTime.UtcNow
        });

        (await _fx.CountAsync(Table)).Should().Be(1);

        await repo.DeleteAllPacketsAsync();

        (await _fx.CountAsync(Table)).Should().Be(0);
    }
}
