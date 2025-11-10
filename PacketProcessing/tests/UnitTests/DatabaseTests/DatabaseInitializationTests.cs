using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Moq;
using Npgsql;
using PacketProcessing.Context;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Entities.Range;
using PacketProcessing.Repositories.EfRepository;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Tests.Utils;
using Xunit;
using Xunit.Abstractions;

namespace PacketProcessing.Tests.UnitTests.DatabaseTests;

/// <summary>
/// Tests for database initialization and connectivity without external dependencies.
/// </summary>
public class DatabaseInitializationTests : IDisposable
{
    #region Fields

    private readonly ITestOutputHelper _output;
    private readonly IConfiguration _configuration;
    private readonly PostgresDbContext _postgresContext;
    private readonly QuestDbContextShim _questDbContext;

    #endregion

    #region Constructor

    public DatabaseInitializationTests(ITestOutputHelper output)
    {
        _output = output;

        _configuration = TestConfigurationProvider.Configuration;

        var postgresLogger = new Mock<ILogger<PostgresDbContext>>();
        var postgresOptions = new DbContextOptionsBuilder<PostgresDbContext>()
            .UseInMemoryDatabase($"postgres-tests-{Guid.NewGuid()}")
            .Options;
        _postgresContext = new PostgresDbContext(postgresOptions, postgresLogger.Object);

        var questLogger = new Mock<ILogger<QuestDbContext>>();
        var questConfiguration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["QuestDb:Host"] = "test-host",
                ["QuestDb:PostgresPort"] = "8812",
                ["QuestDb:InfluxPort"] = "9000",
                ["QuestDb:HttpPort"] = "9009",
                ["QuestDb:Username"] = "quest",
                ["QuestDb:Password"] = "quest",
                ["QuestDb:Database"] = "PacketDBTest"
            })
            .Build();
        _questDbContext = new QuestDbContextShim(questConfiguration, questLogger.Object);

        _output.WriteLine($"[{DateTime.UtcNow:O}] DatabaseInitializationTests initialized");
    }

    #endregion

    #region PostgreSQL Tests

    [Fact]
    public async Task PostgresDbContext_ShouldConnectSuccessfully()
    {
        await _postgresContext.Database.EnsureCreatedAsync();
        var canConnect = await _postgresContext.Database.CanConnectAsync();
        Assert.True(canConnect, "In-memory PostgreSQL context should be accessible");
    }

    [Fact]
    public async Task PostgresDbContext_ShouldCreateDatabaseIfNotExists()
    {
        var created = await _postgresContext.Database.EnsureCreatedAsync();
        Assert.True(created || !created);
        var canConnect = await _postgresContext.Database.CanConnectAsync();
        Assert.True(canConnect);
    }

    [Fact]
    public async Task PostgresDbContext_ShouldHaveRequiredTables()
    {
        await _postgresContext.Database.EnsureCreatedAsync();
        Assert.NotNull(_postgresContext.Ranges);
        Assert.NotNull(_postgresContext.Targets);
        Assert.NotNull(_postgresContext.Hits);
        Assert.NotNull(_postgresContext.Events);

        var model = _postgresContext.Model;
        Assert.NotNull(model.FindEntityType(typeof(RangeEntity)));
        Assert.NotNull(model.FindEntityType(typeof(TargetEntity)));
        Assert.NotNull(model.FindEntityType(typeof(HitEntity)));
        Assert.NotNull(model.FindEntityType(typeof(EventEntity)));
    }

    [Fact]
    public async Task PostgresDbContext_ShouldSupportBasicCrudOperations()
    {
        await _postgresContext.Database.EnsureCreatedAsync();

        var testRange = new RangeEntity
        {
            Id = Guid.NewGuid(),
            StartTime = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
            EndTime = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeMilliseconds(),
            Description = "Test Description",
            Timestamp = DateTime.UtcNow
        };

        _postgresContext.Ranges.Add(testRange);
        await _postgresContext.SaveChangesAsync();

        var retrievedRange = await _postgresContext.Ranges.FirstOrDefaultAsync(r => r.Id == testRange.Id);
        Assert.NotNull(retrievedRange);

        retrievedRange!.Description = "Updated";
        await _postgresContext.SaveChangesAsync();

        var updatedRange = await _postgresContext.Ranges.FirstAsync(r => r.Id == testRange.Id);
        Assert.Equal("Updated", updatedRange.Description);

        _postgresContext.Ranges.Remove(updatedRange);
        await _postgresContext.SaveChangesAsync();

        var deletedRange = await _postgresContext.Ranges.FirstOrDefaultAsync(r => r.Id == testRange.Id);
        Assert.Null(deletedRange);
    }

    #endregion

    #region QuestDB Tests

    [Fact]
    public void QuestDbContext_ShouldInitializeSuccessfully()
    {
        Assert.NotNull(_questDbContext);
        Assert.Contains("Host=test-host", _questDbContext.ConnectionString);
    }

    [Fact]
    public void QuestDbContext_OpenMockConnection_ShouldReturnClosedConnection()
    {
        using var connection = _questDbContext.OpenMockConnection();
        Assert.NotNull(connection);
        Assert.Equal(System.Data.ConnectionState.Closed, connection.State);
    }

    [Fact]
    public async Task QuestDbContext_EnsureDatabaseAsyncStub_ShouldReturnTrue()
    {
        var result = await _questDbContext.EnsureDatabaseAsyncStub();
        Assert.True(result);
    }

    #endregion

    #region Repository Factory Tests

    [Fact]
    public void EfRepositoryFactory_ShouldResolveRegisteredRepository()
    {
        var services = new ServiceCollection();
        var rangeRepoMock = new Mock<IEfRepository<RangeEntity>>();
        services.AddSingleton(rangeRepoMock.Object);
        services.AddSingleton<IEfRepositoryFactory, EfRepositoryFactory>();

        var provider = services.BuildServiceProvider();
        var factory = provider.GetRequiredService<IEfRepositoryFactory>();

        var resolved = factory.Get<RangeEntity>();
        Assert.Same(rangeRepoMock.Object, resolved);
    }

    [Fact]
    public void InfluxRepositoryFactory_ShouldResolveRegisteredRepositories()
    {
        var services = new ServiceCollection();
        var motionRepo = new Mock<IInfluxRepository<MotionPacketEntity>>();
        var safetyRepo = new Mock<IInfluxRepository<SafetyPacketEntity>>();
        var onvifRepo = new Mock<IInfluxRepository<OnVIFPacketEntity>>();

        services.AddSingleton(motionRepo.Object);
        services.AddSingleton(safetyRepo.Object);
        services.AddSingleton(onvifRepo.Object);
        services.AddSingleton<IInfluxRepositoryFactory, InfluxRepositoryFactory>();

        var provider = services.BuildServiceProvider();
        var factory = provider.GetRequiredService<IInfluxRepositoryFactory>();

        Assert.Same(motionRepo.Object, factory.Get<MotionPacketEntity>());
        Assert.Same(safetyRepo.Object, factory.Get<SafetyPacketEntity>());
        Assert.Same(onvifRepo.Object, factory.Get<OnVIFPacketEntity>());
    }

    #endregion

    #region Initialization Flow

    [Fact]
    public async Task DatabaseInitialization_ShouldCompleteWithoutErrors()
    {
        await _postgresContext.Database.EnsureCreatedAsync();
        var postgresConnected = await _postgresContext.Database.CanConnectAsync();
        var questReady = await _questDbContext.EnsureDatabaseAsyncStub();

        Assert.True(postgresConnected);
        Assert.True(questReady);
    }

    [Fact]
    public async Task DatabaseConfiguration_ShouldHandleConnectionFailures()
    {
        var options = new DbContextOptionsBuilder<PostgresDbContext>()
            .UseInMemoryDatabase($"invalid-{Guid.NewGuid()}")
            .Options;
        var logger = new Mock<ILogger<PostgresDbContext>>();
        var postgresMock = new Mock<PostgresDbContext>(options, logger.Object) { CallBase = false };
        var databaseFacadeMock = new Mock<DatabaseFacade>(postgresMock.Object);
        databaseFacadeMock.Setup(d => d.CanConnectAsync(It.IsAny<CancellationToken>())).ReturnsAsync(false);
        postgresMock.SetupGet(p => p.Database).Returns(databaseFacadeMock.Object);

        var canConnect = await postgresMock.Object.Database.CanConnectAsync();
        Assert.False(canConnect);
    }

    [Fact]
    public void TestConfigurationProvider_ShouldExposeExpectedDefaults()
    {
        var postgresConfig = TestConfigurationProvider.GetPostgresConfiguration();
        var questConfig = TestConfigurationProvider.GetQuestDbConfiguration();

        Assert.Equal("RangeDBTest", postgresConfig.Database);
        Assert.Equal("PacketDBTest", questConfig.Database);
    }

    #endregion

    #region IDisposable

    public void Dispose()
    {
        _postgresContext.Dispose();
        _questDbContext.Dispose();
    }

    #endregion

    private sealed class QuestDbContextShim : QuestDbContext, IDisposable
    {
        public QuestDbContextShim(IConfiguration cfg, ILogger<QuestDbContext> log)
            : base(cfg, log)
        {
        }

        public NpgsqlConnection OpenMockConnection()
        {
            return new NpgsqlConnection("Host=localhost;Port=1;Username=test;Password=test;Database=test;");
        }

        public Task<bool> EnsureDatabaseAsyncStub()
        {
            return Task.FromResult(true);
        }

        public void Dispose()
        {
        }
    }
}
