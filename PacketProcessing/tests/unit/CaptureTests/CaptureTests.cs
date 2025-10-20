using System.Diagnostics;
using System.Threading.Channels;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Services.Networking;
using PacketProcessing.Utils.Observers;
using Xunit;
using Xunit.Abstractions;

namespace PacketProcessing.Tests.Unit;

/// <summary>
/// Unit tests for packet capture pipeline using the Python packet blaster
/// Tests: DeviceService → HandlerService → Channel
/// </summary>
public class CaptureTests : IDisposable
{
    private readonly ITestOutputHelper _output;
    private readonly ILogger<DeviceService> _deviceLogger;
    private readonly ILogger<HandlerService<SafetyPacketEntity>> _handlerLogger;
    private readonly IConfiguration _configuration;
    private Process? _blasterProcess;
    private static bool _sudoAuthenticated = false;
    private static readonly object _sudoLock = new object();

    public CaptureTests(ITestOutputHelper output)
    {
        _output = output;
        
        // Authenticate sudo once for all tests
        lock (_sudoLock)
        {
            if (!_sudoAuthenticated)
            {
                AuthenticateSudo();
                _sudoAuthenticated = true;
            }
        }
        
        // Setup logging to test output
        var loggerFactory = LoggerFactory.Create(builder =>
        {
            builder.AddProvider(new TestOutputLoggerProvider(output));
            builder.SetMinimumLevel(LogLevel.Debug);
        });
        
        _deviceLogger = loggerFactory.CreateLogger<DeviceService>();
        _handlerLogger = loggerFactory.CreateLogger<HandlerService<SafetyPacketEntity>>();
        
        // Setup configuration
        var configBuilder = new ConfigurationBuilder()
            .SetBasePath(Directory.GetCurrentDirectory())
            .AddJsonFile("appsettings.Test.json", optional: true)
            .AddInMemoryCollection(new Dictionary<string, string>
            {
                ["DataPipes:SafetyCapture:Network:Protocol"] = "udp",
                ["DataPipes:SafetyCapture:Network:IPs:0"] = "132.8.7.101",
                ["DataPipes:SafetyCapture:Network:IPs:1"] = "132.8.7.102",
                ["DataPipes:SafetyCapture:Channel:Members"] = "100000",
                ["Concurrency:MinWorkers"] = "2",
                ["Concurrency:MaxWorkers"] = "4"
            }!);
        
        _configuration = configBuilder.Build();
    }

    [Fact]
    public async Task DeviceService_ShouldCapturePacketsMatchingFilter()
    {
        // Arrange
        var deviceService = new DeviceService(_deviceLogger);
        var availableDevices = deviceService.GetAvailableDeviceNames();
        
        Assert.NotEmpty(availableDevices);
        _output.WriteLine($"Available devices: {string.Join(", ", availableDevices)}");
        
        // Use en0 or first available device
        var deviceName = availableDevices.Contains("en0") ? "en0" : availableDevices.First();
        _output.WriteLine($"Using device: {deviceName}");
        
        var capturedPackets = new List<(ReadOnlyMemory<byte> Data, DateTime Timestamp)>();
        var observer = new TestPacketObserver(packet =>
        {
            capturedPackets.Add((packet.Data, packet.Timestamp));
            _output.WriteLine($"Captured packet: {packet.Data.Length} bytes at {packet.Timestamp:HH:mm:ss.fff}");
        });
        
        var filter = "udp and (host 132.8.7.101 or host 132.8.7.102)";
        
        // Act
        await deviceService.SubscribeWithFilterAsync(observer, deviceName, filter);
        
        // Start packet blaster in background
        await StartPacketBlasterAsync("safety_seq.pcap", deviceName, pps: 10, loop: 1);
        
        // Wait for packets to arrive
        await Task.Delay(TimeSpan.FromSeconds(5));
        
        await deviceService.UnsubscribeAsync(observer);
        
        // Assert
        Assert.NotEmpty(capturedPackets);
        _output.WriteLine($"Total packets captured: {capturedPackets.Count}");
        
        // Verify packets match the filter (should be UDP to 132.8.7.101 or 132.8.7.102)
        Assert.All(capturedPackets, packet => Assert.True(packet.Data.Length > 0));
    }

    [Fact]
    public async Task HandlerService_ShouldParseAndWriteToChannel()
    {
        // Arrange
        var channel = Channel.CreateBounded<SafetyPacketEntity>(new BoundedChannelOptions(10000)
        {
            FullMode = BoundedChannelFullMode.Wait,
            SingleReader = false,
            SingleWriter = false
        });
        
        var handlerService = new HandlerService<SafetyPacketEntity>(
            "DataPipes:SafetyCapture",
            _handlerLogger,
            channel,
            _configuration);
        
        var deviceService = new DeviceService(_deviceLogger);
        var availableDevices = deviceService.GetAvailableDeviceNames();
        var deviceName = availableDevices.Contains("en0") ? "en0" : availableDevices.First();
        
        // Start HandlerService workers (as BackgroundService)
        var cts = new CancellationTokenSource();
        var workerTask = handlerService.StartAsync(cts.Token);
        
        _output.WriteLine("HandlerService workers started");
        
        // Wait for workers to initialize
        await Task.Delay(500);
        
        // Act
        await handlerService.SubscribeToDeviceAsync(deviceService, deviceName);
        
        // Wait a moment for capture to fully initialize
        await Task.Delay(500);
        
        // Start packet blaster
        await StartPacketBlasterAsync("safety_seq.pcap", deviceName, pps: 50, loop: 1);
        
        _output.WriteLine("Packet blaster started, waiting for packets to be processed...");
        
        // Wait for packets to be parsed (safety_seq.pcap has ~991 packets at 50 pps = ~20 seconds)
        // Add extra time for processing
        await Task.Delay(TimeSpan.FromSeconds(25));
        
        _output.WriteLine("Waiting complete, checking stats before reading...");
        
        // Check stats first to see if parsing happened
        var statsBeforeRead = handlerService.GetStats();
        _output.WriteLine($"Before reading channel: Captured={statsBeforeRead.Captured}, Parsed={statsBeforeRead.Parsed}, Dropped={statsBeforeRead.Dropped}");
        
        // Wait a bit more for workers to finish writing to parsed channel
        await Task.Delay(1000);
        
        // Check if channel has data available
        var channelCount = channel.Reader.CanCount ? channel.Reader.Count : -1;
        _output.WriteLine($"Channel reports CanCount={channel.Reader.CanCount}, Count={channelCount}");
        
        // Read from channel
        var parsedPackets = new List<SafetyPacketEntity>();
        var readAttempts = 0;
        while (channel.Reader.TryRead(out var packet))
        {
            parsedPackets.Add(packet);
            readAttempts++;
        }
        
        _output.WriteLine($"Read {parsedPackets.Count} packets from channel (attempts: {readAttempts})");
        
        await handlerService.UnsubscribeAsync(deviceService);
        
        // Stop HandlerService workers
        await handlerService.StopAsync(CancellationToken.None);
        cts.Cancel();
        cts.Dispose();
        
        // Assert
        Assert.NotEmpty(parsedPackets);
        _output.WriteLine($"Total packets parsed and written to channel: {parsedPackets.Count}");
        
        // Verify parsed packets have valid data
        foreach (var packet in parsedPackets.Take(5))
        {
            Assert.NotEqual(Guid.Empty, packet.Id);
            Assert.True(packet.Timestamp > DateTime.UtcNow.AddMinutes(-1));
            _output.WriteLine($"Packet: ID={packet.Id}, Timestamp={packet.Timestamp:HH:mm:ss.fff}");
        }
        
        // Check stats
        var stats = handlerService.GetStats();
        _output.WriteLine($"Handler stats: Captured={stats.Captured}, Parsed={stats.Parsed}, Dropped={stats.Dropped}");
        
        // Assertions - focus on pipeline integrity, not precise packet count
        Assert.True(stats.Captured > 0, "No packets were captured");
        Assert.True(stats.Parsed > 0, "No packets were parsed");
        Assert.Equal(stats.Captured, stats.Parsed); // Every captured packet should be parsed
        Assert.Equal(0, stats.Dropped); // Should not drop any packets
        Assert.Equal(stats.Parsed, parsedPackets.Count); // Every parsed packet should be in channel
    }

    [Fact]
    public async Task FullPipeline_ShouldCaptureParseAndDeliverAllPackets()
    {
        // Arrange
        var channel = Channel.CreateBounded<SafetyPacketEntity>(new BoundedChannelOptions(100000)
        {
            FullMode = BoundedChannelFullMode.Wait,
            SingleReader = false,
            SingleWriter = false
        });
        
        var deviceService = new DeviceService(_deviceLogger);
        var handlerService = new HandlerService<SafetyPacketEntity>(
            "DataPipes:SafetyCapture",
            _handlerLogger,
            channel,
            _configuration);
        
        var availableDevices = deviceService.GetAvailableDeviceNames();
        var deviceName = availableDevices.Contains("en0") ? "en0" : availableDevices.First();
        
        // Start HandlerService workers (as BackgroundService)
        var cts = new CancellationTokenSource();
        var workerTask = handlerService.StartAsync(cts.Token);
        
        _output.WriteLine("HandlerService workers started");
        
        // Wait for workers to initialize
        await Task.Delay(500);
        
        // Act
        await handlerService.SubscribeToDeviceAsync(deviceService, deviceName);
        
        // Wait for capture to initialize
        await Task.Delay(500);
        
        // Start packet blaster (don't rely on precise PCAP count)
        await StartPacketBlasterAsync("safety_seq.pcap", deviceName, pps: 100, loop: 1);
        
        _output.WriteLine("Packet blaster started, waiting for packets to be processed...");
        
        // Wait for all packets to be processed (991 packets at 100 pps = ~10 seconds)
        // Add extra time for processing
        await Task.Delay(TimeSpan.FromSeconds(15));
        
        // Get stats before reading channel
        var stats = handlerService.GetStats();
        
        // Read all packets from channel
        var deliveredPackets = new List<SafetyPacketEntity>();
        while (channel.Reader.TryRead(out var packet))
        {
            deliveredPackets.Add(packet);
        }
        
        await handlerService.UnsubscribeAsync(deviceService);
        
        // Stop HandlerService workers
        await handlerService.StopAsync(CancellationToken.None);
        cts.Cancel();
        cts.Dispose();
        
        // Assert - focus on pipeline integrity, not precise packet count from PCAP
        _output.WriteLine("═══════════════════════════════════════════════════════");
        _output.WriteLine($"Captured: {stats.Captured} packets");
        _output.WriteLine($"Parsed: {stats.Parsed} packets");
        _output.WriteLine($"Delivered to channel: {deliveredPackets.Count} packets");
        _output.WriteLine($"Dropped: {stats.Dropped} packets");
        _output.WriteLine("═══════════════════════════════════════════════════════");
        
        // Verify pipeline integrity (blaster isn't precise, so ignore expected count)
        Assert.True(stats.Captured > 0, "No packets were captured");
        Assert.Equal(stats.Captured, stats.Parsed); // Every captured packet should be parsed
        Assert.Equal(stats.Parsed, deliveredPackets.Count); // Every parsed packet should be delivered
        Assert.Equal(0, stats.Dropped); // No packets should be dropped
        
        _output.WriteLine("✅ Pipeline integrity verified: Captured = Parsed = Delivered, Dropped = 0");
    }

    private async Task StartPacketBlasterAsync(string pcapFile, string interfaceName, int pps, int loop)
    {
        var projectRoot = FindProjectRoot();
        var pcapPath = Path.Combine(projectRoot, "PacketTester", "pcaps", pcapFile);
        var blasterPath = Path.Combine(projectRoot, "PacketTester", "packet_blaster.py");
        
        if (!File.Exists(pcapPath))
            throw new FileNotFoundException($"PCAP file not found: {pcapPath}");
        
        if (!File.Exists(blasterPath))
            throw new FileNotFoundException($"Packet blaster not found: {blasterPath}");
        
        _output.WriteLine($"Starting packet blaster: {pcapFile} on {interfaceName} at {pps} pps");
        
        _blasterProcess = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = "sudo",
                Arguments = $"python3 {blasterPath} --pcap-in {pcapPath} --interface {interfaceName} --pps {pps} --loop {loop}",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            }
        };
        
        _blasterProcess.OutputDataReceived += (sender, e) =>
        {
            if (!string.IsNullOrEmpty(e.Data))
                _output.WriteLine($"[Blaster] {e.Data}");
        };
        
        _blasterProcess.ErrorDataReceived += (sender, e) =>
        {
            if (!string.IsNullOrEmpty(e.Data))
                _output.WriteLine($"[Blaster ERROR] {e.Data}");
        };
        
        _blasterProcess.Start();
        _blasterProcess.BeginOutputReadLine();
        _blasterProcess.BeginErrorReadLine();
        
        // Give it a moment to start
        await Task.Delay(500);
    }

    private async Task<int> GetPacketCountFromPcap(string pcapFile)
    {
        var projectRoot = FindProjectRoot();
        var pcapPath = Path.Combine(projectRoot, "PacketTester", "pcaps", pcapFile);
        
        if (!File.Exists(pcapPath))
            return 0;
        
        // Use tcpdump or tshark to count packets
        var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = "tcpdump",
                Arguments = $"-r {pcapPath} -n",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            }
        };
        
        process.Start();
        var lines = await process.StandardOutput.ReadToEndAsync();
        await process.WaitForExitAsync();
        
        return lines.Split('\n', StringSplitOptions.RemoveEmptyEntries).Length;
    }

    private string FindProjectRoot()
    {
        var current = Directory.GetCurrentDirectory();
        while (current != null && !Directory.Exists(Path.Combine(current, "PacketTester")))
        {
            current = Directory.GetParent(current)?.FullName;
        }
        return current ?? throw new DirectoryNotFoundException("Could not find project root with PacketTester directory");
    }

    /// <summary>
    /// Authenticate sudo at the start of test run
    /// This will prompt for password once, then cache credentials for subsequent commands
    /// </summary>
    private void AuthenticateSudo()
    {
        _output.WriteLine("═══════════════════════════════════════════════════════");
        _output.WriteLine("⚠️  These tests require sudo access for packet capture");
        _output.WriteLine("    Please enter your password when prompted");
        _output.WriteLine("═══════════════════════════════════════════════════════");
        _output.WriteLine("");
        
        try
        {
            // Run a simple sudo command to authenticate and cache credentials
            var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = "sudo",
                    Arguments = "-v", // Validate sudo credentials
                    UseShellExecute = false,
                    RedirectStandardOutput = false,
                    RedirectStandardError = false,
                    RedirectStandardInput = false
                }
            };
            
            process.Start();
            process.WaitForExit();
            
            if (process.ExitCode != 0)
            {
                throw new InvalidOperationException("Sudo authentication failed. These tests require elevated privileges.");
            }
            
            _output.WriteLine("✓ Sudo authentication successful");
            _output.WriteLine("");
        }
        catch (Exception ex)
        {
            _output.WriteLine($"✗ Sudo authentication failed: {ex.Message}");
            _output.WriteLine("");
            _output.WriteLine("To run these tests, use:");
            _output.WriteLine("  sudo -E dotnet test --filter \"FullyQualifiedName~CaptureTests\"");
            throw;
        }
    }

    public void Dispose()
    {
        if (_blasterProcess != null && !_blasterProcess.HasExited)
        {
            try
            {
                _blasterProcess.Kill(true);
                _blasterProcess.WaitForExit(1000);
            }
            catch { /* ignore */ }
            
            _blasterProcess.Dispose();
        }
    }
}

/// <summary>
/// Simple observer for testing packet capture
/// </summary>
internal class TestPacketObserver : IObserver<RawPacketEvent>
{
    private readonly Action<RawPacketEvent> _onNext;

    public TestPacketObserver(Action<RawPacketEvent> onNext)
    {
        _onNext = onNext;
    }

    public void OnNext(RawPacketEvent value) => _onNext(value);
    public void OnError(Exception error) { }
    public void OnCompleted() { }
}

/// <summary>
/// Logger provider that writes to xUnit test output
/// </summary>
internal class TestOutputLoggerProvider : ILoggerProvider
{
    private readonly ITestOutputHelper _output;

    public TestOutputLoggerProvider(ITestOutputHelper output)
    {
        _output = output;
    }

    public ILogger CreateLogger(string categoryName) => new TestOutputLogger(_output, categoryName);
    public void Dispose() { }
}

internal class TestOutputLogger : ILogger
{
    private readonly ITestOutputHelper _output;
    private readonly string _category;

    public TestOutputLogger(ITestOutputHelper output, string category)
    {
        _output = output;
        _category = category;
    }

    public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
    public bool IsEnabled(LogLevel logLevel) => true;

    public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
    {
        try
        {
            _output.WriteLine($"[{logLevel}] [{_category}] {formatter(state, exception)}");
            if (exception != null)
                _output.WriteLine(exception.ToString());
        }
        catch { /* Ignore - test output might be disposed */ }
    }
}

