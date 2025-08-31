using System.Net;
using System.Net.Sockets;
using System.Text;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Tests.Unit.NetworkingTests;

public class MockPacketServer : IDisposable
{
    private readonly string _protocol;
    private readonly string _packetType;
    private readonly int _packetsPerSecond;
    private readonly int _runtimeSeconds;
    private readonly Random _random;
    private readonly CancellationTokenSource _cancellationTokenSource;
    
    private TcpListener? _tcpListener;
    private UdpClient? _udpClient;
    private HttpListener? _httpListener;
    private Task? _serverTask;
    private bool _isRunning;

    public MockPacketServer(
        string protocol,
        string packetType,
        int packetsPerSecond,
        int runtimeSeconds)
    {
        _protocol = protocol.ToLower();
        _packetType = packetType.ToLower();
        _packetsPerSecond = packetsPerSecond;
        _runtimeSeconds = runtimeSeconds;
        _random = new Random();
        _cancellationTokenSource = new CancellationTokenSource();
        
        ValidateConfiguration();
    }

    private void ValidateConfiguration()
    {
        if (!new[] { "tcp", "udp", "http" }.Contains(_protocol))
            throw new ArgumentException("Protocol must be 'tcp', 'udp', or 'http'", nameof(_protocol));
            
        if (!new[] { "motion", "safety", "onvif" }.Contains(_packetType))
            throw new ArgumentException("Packet type must be 'motion', 'safety', or 'onvif'", nameof(_packetType));
            
        if (_packetsPerSecond <= 0)
            throw new ArgumentException("Packets per second must be greater than 0", nameof(_packetsPerSecond));
            
        if (_runtimeSeconds <= 0)
            throw new ArgumentException("Runtime seconds must be greater than 0", nameof(_runtimeSeconds));
    }

    public async Task StartServerAsync()
    {
        if (_isRunning)
            throw new InvalidOperationException("Server is already running");

        Console.WriteLine($"Starting MockPacketServer:");
        Console.WriteLine($"  Protocol: {_protocol}");
        Console.WriteLine($"  Packet Type: {_packetType}");
        Console.WriteLine($"  Packets per second: {_packetsPerSecond}");
        Console.WriteLine($"  Runtime: {_runtimeSeconds} seconds");
        Console.WriteLine();

        _isRunning = true;

        switch (_protocol)
        {
            case "tcp":
                await StartTcpServerAsync();
                break;
            case "udp":
                await StartUdpServerAsync();
                break;
            case "http":
                await StartHttpServerAsync();
                break;
        }
    }

    private Task StartTcpServerAsync()
    {
        _tcpListener = new TcpListener(IPAddress.Any, 0); // Port 0 means any available port
        _tcpListener.Start();
        
        var actualPort = ((IPEndPoint)_tcpListener.LocalEndpoint).Port;
        Console.WriteLine($"TCP Server listening on port {actualPort}");
        
        _serverTask = Task.Run(async () =>
        {
            var startTime = DateTime.UtcNow;
            var endTime = startTime.AddSeconds(_runtimeSeconds);
            var delayBetweenPackets = TimeSpan.FromMilliseconds(1000.0 / _packetsPerSecond);
            var packetCount = 0;

            try
            {
                while (DateTime.UtcNow < endTime && !_cancellationTokenSource.Token.IsCancellationRequested)
                {
                    // Accept any incoming connection
                    var client = await _tcpListener.AcceptTcpClientAsync(_cancellationTokenSource.Token);
                    
                    // Handle client in background
                    _ = Task.Run(async () =>
                    {
                        try
                        {
                            using (client)
                            {
                                var stream = client.GetStream();
                                
                                while (DateTime.UtcNow < endTime && !_cancellationTokenSource.Token.IsCancellationRequested)
                                {
                                    var packet = GenerateRandomPacket();
                                    var packetData = SerializePacket(packet);
                                    var data = Encoding.UTF8.GetBytes(packetData);
                                    
                                    await stream.WriteAsync(data, 0, data.Length);
                                    packetCount++;
                                    
                                    if (packetCount % 100 == 0)
                                    {
                                        Console.WriteLine($"Sent {packetCount} TCP packets...");
                                    }
                                    
                                    await Task.Delay(delayBetweenPackets, _cancellationTokenSource.Token);
                                }
                            }
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine($"TCP client error: {ex.Message}");
                        }
                    }, _cancellationTokenSource.Token);
                }
            }
            catch (OperationCanceledException)
            {
                Console.WriteLine("TCP Server was cancelled.");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"TCP Server error: {ex.Message}");
            }
        }, _cancellationTokenSource.Token);

        return _serverTask;
    }

    private Task StartUdpServerAsync()
    {
        _udpClient = new UdpClient(0); // Port 0 means any available port
        
        var localEndPoint = _udpClient.Client.LocalEndPoint as IPEndPoint;
        if (localEndPoint == null)
        {
            throw new InvalidOperationException("Failed to get local endpoint from UDP client");
        }
        
        var actualPort = localEndPoint.Port;
        Console.WriteLine($"UDP Server listening on port {actualPort}");
        
        _serverTask = Task.Run(async () =>
        {
            var startTime = DateTime.UtcNow;
            var endTime = startTime.AddSeconds(_runtimeSeconds);
            var delayBetweenPackets = TimeSpan.FromMilliseconds(1000.0 / _packetsPerSecond);
            var packetCount = 0;

            try
            {
                while (DateTime.UtcNow < endTime && !_cancellationTokenSource.Token.IsCancellationRequested)
                {
                    var packet = GenerateRandomPacket();
                    var packetData = SerializePacket(packet);
                    var data = Encoding.UTF8.GetBytes(packetData);
                    
                    // Send to any client that might be listening (broadcast-like behavior for testing)
                    await _udpClient.SendAsync(data, data.Length, "127.0.0.1", actualPort);
                    packetCount++;
                    
                    if (packetCount % 100 == 0)
                    {
                        Console.WriteLine($"Sent {packetCount} UDP packets...");
                    }
                    
                    await Task.Delay(delayBetweenPackets, _cancellationTokenSource.Token);
                }
            }
            catch (OperationCanceledException)
            {
                Console.WriteLine("UDP Server was cancelled.");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"UDP Server error: {ex.Message}");
            }
        }, _cancellationTokenSource.Token);

        return _serverTask;
    }

    private Task StartHttpServerAsync()
    {
        _httpListener = new HttpListener();
        _httpListener.Prefixes.Add("http://localhost:0/"); // Port 0 means any available port
        _httpListener.Start();
        
        // Note: HttpListener doesn't easily expose the actual port, so we'll just show it's listening
        Console.WriteLine($"HTTP Server listening on any available port");
        
        _serverTask = Task.Run(async () =>
        {
            var startTime = DateTime.UtcNow;
            var endTime = startTime.AddSeconds(_runtimeSeconds);
            var delayBetweenPackets = TimeSpan.FromMilliseconds(1000.0 / _packetsPerSecond);
            var packetCount = 0;

            try
            {
                while (DateTime.UtcNow < endTime && !_cancellationTokenSource.Token.IsCancellationRequested)
                {
                    var context = await _httpListener.GetContextAsync();
                    
                    // Handle request in background
                    _ = Task.Run(async () =>
                    {
                        try
                        {
                            var packet = GenerateRandomPacket();
                            var packetData = SerializePacket(packet);
                            var data = Encoding.UTF8.GetBytes(packetData);
                            
                            context.Response.ContentType = "application/json";
                            context.Response.ContentLength64 = data.Length;
                            await context.Response.OutputStream.WriteAsync(data, 0, data.Length);
                            context.Response.Close();
                            
                            packetCount++;
                            if (packetCount % 100 == 0)
                            {
                                Console.WriteLine($"Sent {packetCount} HTTP packets...");
                            }
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine($"HTTP request error: {ex.Message}");
                            context.Response.StatusCode = 500;
                            context.Response.Close();
                        }
                    }, _cancellationTokenSource.Token);
                    
                    await Task.Delay(delayBetweenPackets, _cancellationTokenSource.Token);
                }
            }
            catch (OperationCanceledException)
            {
                Console.WriteLine("HTTP Server was cancelled.");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"HTTP Server error: {ex.Message}");
            }
        }, _cancellationTokenSource.Token);

        return _serverTask;
    }

    public void Stop()
    {
        if (!_isRunning) return;
        
        Console.WriteLine("Stopping MockPacketServer...");
        _cancellationTokenSource.Cancel();
        _isRunning = false;
        
        _tcpListener?.Stop();
        _udpClient?.Close();
        _httpListener?.Stop();
        
        Console.WriteLine("MockPacketServer stopped.");
    }

    public async Task WaitForCompletionAsync()
    {
        if (_serverTask != null)
        {
            await _serverTask;
        }
    }

    public int GetTcpPort()
    {
        if (_tcpListener?.LocalEndpoint is IPEndPoint endPoint)
        {
            return endPoint.Port;
        }
        return -1;
    }

    private BasePacketEntity GenerateRandomPacket()
    {
        return _packetType switch
        {
            "motion" => GenerateRandomMotionPacket(),
            "safety" => GenerateRandomSafetyPacket(),
            "onvif" => GenerateRandomOnVIFPacket(),
            _ => throw new InvalidOperationException($"Unknown packet type: {_packetType}")
        };
    }

    private MotionPacketEntity GenerateRandomMotionPacket()
    {
        var opCodes = new[] { "MOVE", "STOP", "ROTATE", "SCALE", "TRANSLATE" };
        var descriptions = new[] { "Linear movement", "Stop motion", "Rotational motion", "Scaling operation", "Translation operation" };
        
        return new MotionPacketEntity
        {
            Id = Guid.NewGuid(),
            Timestamp = DateTime.UtcNow,
            Type = _random.Next(2) == 1,
            OpCode = opCodes[_random.Next(opCodes.Length)],
            OpCodeDescription = descriptions[_random.Next(descriptions.Length)],
            Axis = _random.Next(6), // 0-5 for X, Y, Z, RX, RY, RZ
            FloatValue = _random.Next(2) == 1 ? (float?)(_random.NextSingle() * 100) : null
        };
    }

    private SafetyPacketEntity GenerateRandomSafetyPacket()
    {
        var opCodes = new[] { "CHECK", "ALERT", "RESET", "MONITOR", "SHUTDOWN" };
        var descriptions = new[] { "Safety check", "Safety alert", "Reset safety", "Monitor safety", "Safety shutdown" };
        var states = new[] { "SAFE", "WARNING", "DANGER", "CRITICAL", "NORMAL" };
        
        return new SafetyPacketEntity
        {
            Id = Guid.NewGuid(),
            Timestamp = DateTime.UtcNow,
            Type = _random.Next(2) == 1,
            OpCode = opCodes[_random.Next(opCodes.Length)],
            OpCodeDescription = descriptions[_random.Next(descriptions.Length)],
            State = states[_random.Next(states.Length)]
        };
    }

    private OnVIFPacketEntity GenerateRandomOnVIFPacket()
    {
        var descriptions = new[] { "Camera motion", "Zoom operation", "Pan operation", "Tilt operation", "Focus adjustment" };
        
        return new OnVIFPacketEntity
        {
            Id = Guid.NewGuid(),
            Timestamp = DateTime.UtcNow,
            Type = _random.Next(2) == 1,
            Description = descriptions[_random.Next(descriptions.Length)],
            Zoom = _random.Next(2) == 1 ? (float?)(_random.NextSingle() * 10) : null,
            Measurement = _random.NextSingle() * 1000
        };
    }

    private string SerializePacket(BasePacketEntity packet)
    {
        // Simple JSON serialization for testing purposes
        var json = packet switch
        {
            MotionPacketEntity motion => $"{{\"packetType\":\"motion\",\"id\":\"{motion.Id}\",\"timestamp\":\"{motion.Timestamp:O}\",\"type\":{motion.Type.ToString().ToLower()},\"opCode\":\"{motion.OpCode}\",\"opCodeDescription\":\"{motion.OpCodeDescription}\",\"axis\":{motion.Axis},\"floatValue\":{(motion.FloatValue?.ToString() ?? "null")}}}",
            SafetyPacketEntity safety => $"{{\"packetType\":\"safety\",\"id\":\"{safety.Id}\",\"timestamp\":\"{safety.Timestamp:O}\",\"type\":{safety.Type.ToString().ToLower()},\"opCode\":\"{safety.OpCode}\",\"opCodeDescription\":\"{safety.OpCodeDescription}\",\"state\":\"{safety.State}\"}}",
            OnVIFPacketEntity onvif => $"{{\"packetType\":\"onvif\",\"id\":\"{onvif.Id}\",\"timestamp\":\"{onvif.Timestamp:O}\",\"type\":{onvif.Type.ToString().ToLower()},\"description\":\"{onvif.Description}\",\"zoom\":{(onvif.Zoom?.ToString() ?? "null")},\"measurement\":{onvif.Measurement}}}",
            _ => throw new InvalidOperationException($"Unknown packet type: {packet.GetType().Name}")
        };
        
        return json;
    }

    public void Dispose()
    {
        Stop();
        _cancellationTokenSource?.Dispose();
    }
}
