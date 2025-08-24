using PacketProcessing.Entities;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Tests.unit.RepositoryTests;

[Collection(nameof(RepositoryTestsCollection))]
public class MotionRepositoryTests
{
    private readonly QuestDbFixture _fx;
    private const string Table = "motion_packets";

    public MotionRepositoryTests(QuestDbFixture fx) => _fx = fx;

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
        var repo = _fx.CreateRepository<MotionPacketEntity>();

        var now = DateTime.UtcNow;
        var e = new MotionPacketEntity
        {
            Type = true,
            OpCode = "SINGLE",
            OpCodeDescription = "one",
            Axis = 1,
            FloatValue = 1.23f,
            Timestamp = now
        };

        await repo.WriteAsync(_fx._Sender, e);

        var all = (await repo.GetAllPacketsAsync()).ToList();
        all.Should().HaveCount(1);
        all[0].OpCode.Should().Be("SINGLE");
        all[0].Axis.Should().Be(1);
        all[0].Type.Should().BeTrue();
        all[0].FloatValue.Should().BeApproximately(1.23f, 1e-4f);
    }

    [Fact]
    public async Task Write_Batch_Then_Read_Paged()
    {
        await _fx._Qdb.ExecuteAsync($"truncate table \"{Table}\"");
        var repo = _fx.CreateRepository<MotionPacketEntity>();

        var now = DateTime.UtcNow;
        var batch = Enumerable.Range(0, 10)
            .Select(i => new MotionPacketEntity
            {
                Type = i % 2 == 0,
                OpCode = $"B{i:D2}",
                OpCodeDescription = "batch",
                Axis = i,
                FloatValue = i * 0.5f,
                Timestamp = now.AddMilliseconds(i)
            })
            .ToList();

        await repo.WriteBatchAsync(_fx._Sender, batch);

        var page1 = (await repo.GetPaginatedPacketsBetweenTimestampsAsync(
            now.AddMinutes(-1), now.AddMinutes(1), OrderBy.Asc, page: 1, pageSize: 4)).ToList();
        page1.Should().HaveCount(4);
        page1.First().OpCode.Should().Be("B00");

        var page3 = (await repo.GetPaginatedPacketsBetweenTimestampsAsync(
            now.AddMinutes(-1), now.AddMinutes(1), OrderBy.Asc, page: 3, pageSize: 4)).ToList();
        page3.Should().HaveCount(2);
        page3.Last().OpCode.Should().Be("B09");
    }

    [Fact]
    public async Task DeleteAll_Truncates_Table()
    {
        await _fx._Qdb.ExecuteAsync($"truncate table \"{Table}\"");
        var repo = _fx.CreateRepository<MotionPacketEntity>();

        await repo.WriteAsync(_fx._Sender, new MotionPacketEntity
        {
            Type = false,
            OpCode = "X",
            OpCodeDescription = "to-delete",
            Axis = 9,
            FloatValue = 9.9f,
            Timestamp = DateTime.UtcNow
        });

        (await _fx.CountAsync(Table)).Should().Be(1);

        await repo.DeleteAllPacketsAsync();

        (await _fx.CountAsync(Table)).Should().Be(0);
    }
}
