using System.Buffers.Binary;
using System.Net;
using System.Net.Sockets;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Entities.Range;
using SharpPcap;
using PacketDotNet;

namespace PacketProcessing.Tests.Unit.NetworkingTests;

/// <summary>
/// Mock packet server that generates binary packets matching parser expectations
/// </summary>
public class BinaryMockPacketServer : IDisposable
{
    private readonly string _protocol;
    private readonly string _entityType;
    private readonly int _packetsPerSecond;
    private readonly int _runtimeSeconds;
    private readonly Random _random;
    private readonly CancellationTokenSource _cancellationTokenSource;
    
    private TcpListener? _tcpListener;
    private UdpClient? _udpClient;
    private HttpListener? _httpListener;
    private int _httpPort;
    private Task? _serverTask;
    private bool _isRunning;
    private IInjectionDevice? _rawPacketDevice;

    public BinaryMockPacketServer(
        string protocol,
        string entityType,
        int packetsPerSecond,
        int runtimeSeconds)
    {
        _protocol = protocol.ToLower();
        _entityType = entityType.ToLower();
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
            
        if (!new[] { "motion", "safety", "onvif", "event", "hit", "range", "target" }.Contains(_entityType))
            throw new ArgumentException("Entity type must be 'motion', 'safety', 'onvif', 'event', 'hit', 'range', or 'target'", nameof(_entityType));
            
        if (_packetsPerSecond <= 0)
            throw new ArgumentException("Packets per second must be greater than 0", nameof(_packetsPerSecond));
            
        if (_runtimeSeconds <= 0)
            throw new ArgumentException("Runtime seconds must be greater than 0", nameof(_runtimeSeconds));
    }

    public async Task StartServerAsync()
    {
        if (_isRunning)
            throw new InvalidOperationException("Server is already running");

        Console.WriteLine($"Starting BinaryMockPacketServer:");
        Console.WriteLine($"  Protocol: {_protocol}");
        Console.WriteLine($"  Entity Type: {_entityType}");
        Console.WriteLine($"  Packets per second: {_packetsPerSecond}");
        Console.WriteLine($"  Runtime: {_runtimeSeconds} seconds");
        Console.WriteLine();

        _isRunning = true;

        // Use raw packet sending for all protocols to test actual packet capture performance
        _ = StartRawPacketSenderAsync();
        // Return immediately after starting
        await Task.Yield();
    }

    private Task StartTcpServerAsync()
    {
        // For HTTP protocol, bind to port 8080 to match capture filter
        int port = _protocol == "http" ? 8080 : 0;
        _tcpListener = new TcpListener(IPAddress.Any, port);
        _tcpListener.Start();
        
        var actualPort = ((IPEndPoint)_tcpListener.LocalEndpoint).Port;
        Console.WriteLine($"TCP Server listening on port {actualPort}");
        
        var serverLoop = Task.Run(async () =>
        {
            try
            {
                while (!_cancellationTokenSource.Token.IsCancellationRequested)
                {
                    var client = await _tcpListener.AcceptTcpClientAsync(_cancellationTokenSource.Token);
                    
                    _ = Task.Run(async () =>
                    {
                        try
                        {
                            using (client)
                            {
                                var stream = client.GetStream();
                                
                                // Read the HTTP request
                                var buffer = new byte[4096];
                                var bytesRead = await stream.ReadAsync(buffer, 0, buffer.Length);
                                
                                // Send HTTP response with binary data
                                var packetData = GenerateBinaryPacket();
                                var response = $"HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nContent-Length: {packetData.Length}\r\n\r\n";
                                var responseBytes = System.Text.Encoding.ASCII.GetBytes(response);
                                
                                await stream.WriteAsync(responseBytes, 0, responseBytes.Length);
                                await stream.WriteAsync(packetData, 0, packetData.Length);
                                
                                stream.Close();
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

        // Client loop to generate HTTP requests to our listener, producing TCP traffic on loopback
        var clientLoop = Task.Run(async () =>
        {
            var startTime = DateTime.UtcNow;
            var endTime = startTime.AddSeconds(_runtimeSeconds);
            var delayBetweenPackets = TimeSpan.FromMilliseconds(1000.0 / _packetsPerSecond);
            var packetCount = 0;

            try
            {
                while (DateTime.UtcNow < endTime && !_cancellationTokenSource.Token.IsCancellationRequested)
                {
                    try
                    {
                        // Create a new TCP connection for each request to ensure plain HTTP
                        using var tcpClient = new TcpClient();
                        tcpClient.Connect("localhost", actualPort);
                        using var stream = tcpClient.GetStream();
                        
                        var packetData = GenerateBinaryPacket();
                        
                        if (_protocol == "http")
                        {
                            // Create a simple HTTP POST request for HTTP protocol
                            var httpRequest = $"POST / HTTP/1.1\r\n" +
                                            $"Host: localhost:{actualPort}\r\n" +
                                            $"Content-Type: application/octet-stream\r\n" +
                                            $"Content-Length: {packetData.Length}\r\n" +
                                            $"Connection: close\r\n" +
                                            $"\r\n";
                            
                            var httpRequestBytes = System.Text.Encoding.ASCII.GetBytes(httpRequest);
                            
                            // Send HTTP headers
                            await stream.WriteAsync(httpRequestBytes, 0, httpRequestBytes.Length);
                            
                            // Send binary data
                            await stream.WriteAsync(packetData, 0, packetData.Length);
                        }
                        else
                        {
                            // Send raw binary data for TCP protocol (Motion packets)
                            await stream.WriteAsync(packetData, 0, packetData.Length);
                        }
                        
                        // Close the connection immediately
                        stream.Close();
                        tcpClient.Close();
                        
                        packetCount++;
                        
                        // Reduced logging for cleaner output
                        if (packetCount % 1000 == 0)
                        {
                            var protocolName = _protocol == "http" ? "HTTP requests" : "TCP packets";
                            Console.WriteLine($"Sent {packetCount} {protocolName}...");
                        }
                    }
                    catch (Exception ex)
                    {
                        var protocolName = _protocol == "http" ? "HTTP" : "TCP";
                        Console.WriteLine($"{protocolName} client error: {ex.Message}");
                    }
                    
                    await Task.Delay(delayBetweenPackets, _cancellationTokenSource.Token);
                }
            }
            catch (OperationCanceledException)
            {
                Console.WriteLine("HTTP Client was cancelled.");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"HTTP Client error: {ex.Message}");
            }
        }, _cancellationTokenSource.Token);

        _serverTask = Task.WhenAll(serverLoop, clientLoop);
        return _serverTask;
    }

    private Task StartUdpServerAsync()
    {
        _udpClient = new UdpClient(0);
        
        var localEndPoint = _udpClient.Client.LocalEndPoint as IPEndPoint;
        if (localEndPoint == null)
        {
            throw new InvalidOperationException("Failed to get local endpoint from UDP client");
        }
        
        var actualPort = localEndPoint.Port;
        Console.WriteLine($"UDP Server listening on port {actualPort}");
        
        var serverLoop = Task.Run(async () =>
        {
            var startTime = DateTime.UtcNow;
            var endTime = startTime.AddSeconds(_runtimeSeconds);
            var delayBetweenPackets = TimeSpan.FromMilliseconds(1000.0 / _packetsPerSecond);
            var packetCount = 0;

            try
            {
                while (DateTime.UtcNow < endTime && !_cancellationTokenSource.Token.IsCancellationRequested)
                {
                    var packetData = GenerateBinaryPacket();
                    
                    await _udpClient.SendAsync(packetData, packetData.Length, "127.0.0.1", actualPort);
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

        // Client loop to generate HTTP requests to our listener, producing TCP traffic on loopback
        var clientLoop = Task.Run(async () =>
        {
            var startTime = DateTime.UtcNow;
            var endTime = startTime.AddSeconds(_runtimeSeconds);
            var delayBetweenPackets = TimeSpan.FromMilliseconds(1000.0 / _packetsPerSecond);
            using var httpClient = new HttpClient();
            httpClient.Timeout = TimeSpan.FromMilliseconds(500);
            var uri = new Uri($"http://localhost:{_httpPort}/");
            while (DateTime.UtcNow < endTime && !_cancellationTokenSource.Token.IsCancellationRequested)
            {
                try
                {
                    using var req = new HttpRequestMessage(HttpMethod.Post, uri)
                    {
                        Content = new ByteArrayContent(new byte[] { 1 })
                    };
                    using var resp = await httpClient.SendAsync(req, _cancellationTokenSource.Token);
                    _ = await resp.Content.ReadAsByteArrayAsync(_cancellationTokenSource.Token);
                }
                catch { /* ignore transient errors */ }
                await Task.Delay(delayBetweenPackets, _cancellationTokenSource.Token);
            }
        }, _cancellationTokenSource.Token);

        _serverTask = Task.WhenAll(serverLoop, clientLoop);
        return _serverTask;
    }

    private Task StartHttpServerAsync()
    {
        _httpListener = new HttpListener();
        // HttpListener does not support port 0. Bind to a loopback port explicitly.
        // Pick a random available port and add the prefix.
        int port;
        // Prefer 8080 to match capture filter; fallback to random high port if unavailable
        try
        {
            port = 8080;
            _httpListener.Prefixes.Clear();
            _httpListener.Prefixes.Add($"http://localhost:{port}/");
            _httpListener.Start();
            _httpPort = port;
        }
        catch
        {
            var rnd = new Random();
            while (true)
            {
                port = rnd.Next(10240, 65535);
                try
                {
                    _httpListener.Prefixes.Clear();
                    _httpListener.Prefixes.Add($"http://localhost:{port}/");
                    _httpListener.Start();
                    _httpPort = port;
                    break;
                }
                catch
                {
                    // try another port
                }
            }
        }
        
        Console.WriteLine($"HTTP Server listening on port {port}");
        
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
                    HttpListenerContext context;
                    try
                    {
                        context = await _httpListener.GetContextAsync();
                    }
                    catch (ObjectDisposedException)
                    {
                        return; // listener closed during shutdown
                    }
                    catch (HttpListenerException)
                    {
                        return; // stopping listener
                    }
                    
                    _ = Task.Run(async () =>
                    {
                        try
                        {
                            var packetData = GenerateBinaryPacket();
                            
                            context.Response.ContentType = "application/octet-stream";
                            context.Response.ContentLength64 = packetData.Length;
                            await context.Response.OutputStream.WriteAsync(packetData, 0, packetData.Length);
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
                // normal shutdown
            }
            catch (Exception ex)
            {
                Console.WriteLine($"HTTP Server error: {ex.Message}");
            }
        }, _cancellationTokenSource.Token);

        return _serverTask;
    }

    private async Task StartRawPacketSenderAsync()
    {
        try
        {
            // Get the loopback interface for sending raw packets
            var devices = CaptureDeviceList.Instance;
            var loopbackDevice = devices.FirstOrDefault(d => d.Name.Contains("lo0") || d.Name.Contains("loopback"));
            
            if (loopbackDevice == null)
            {
                Console.WriteLine("⚠ No loopback device found, using first available device");
                loopbackDevice = devices.FirstOrDefault();
            }
            
            if (loopbackDevice == null)
            {
                throw new InvalidOperationException("No network devices available for raw packet sending");
            }
            
            // Cast to IInjectionDevice for packet sending
            _rawPacketDevice = loopbackDevice as IInjectionDevice;
            if (_rawPacketDevice == null)
            {
                throw new InvalidOperationException($"Device {loopbackDevice.Name} does not support packet injection");
            }
            Console.WriteLine($"✓ Using device for raw packet sending: {_rawPacketDevice.Name}");
            
            // Open the device for packet injection
            _rawPacketDevice.Open(DeviceModes.Promiscuous, 1000);
            Console.WriteLine("✓ Raw packet device opened for injection");
            
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
                        var packetData = GenerateBinaryPacket();
                        
                        // Send raw packet using SharpPcap
                        await SendRawPacketAsync(packetData);
                        
                        packetCount++;
                        
                        // Log progress every 1000 packets
                        if (packetCount % 1000 == 0)
                        {
                            Console.WriteLine($"Sent {packetCount} raw {_protocol} packets...");
                        }
                        
                        await Task.Delay(delayBetweenPackets, _cancellationTokenSource.Token);
                    }
                }
                catch (OperationCanceledException)
                {
                    Console.WriteLine("Raw packet sender was cancelled.");
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Raw packet sender error: {ex.Message}");
                }
            }, _cancellationTokenSource.Token);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Failed to start raw packet sender: {ex.Message}");
            _isRunning = false;
        }
    }

    private async Task SendRawPacketAsync(byte[] packetData)
    {
        try
        {
            if (_rawPacketDevice == null) return;
            
            // Create a Packet object from the raw data
            var packet = new RawCapture(LinkLayers.Ethernet, new PosixTimeval(), packetData);
            
            // Send the raw packet
            _rawPacketDevice.SendPacket(packet);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error sending raw packet: {ex.Message}");
        }
    }

    public void Stop()
    {
        if (!_isRunning) return;
        
        Console.WriteLine("Stopping BinaryMockPacketServer...");
        _isRunning = false;
        _cancellationTokenSource.Cancel();
        
        try { _tcpListener?.Stop(); } catch { }
        try { _udpClient?.Close(); } catch { }
        try { _httpListener?.Close(); } catch { }
        try { _rawPacketDevice?.Close(); } catch { }
        
        // Wait for server task to complete with timeout
        try
        {
            _serverTask?.Wait(TimeSpan.FromSeconds(2));
        }
        catch (TimeoutException)
        {
            Console.WriteLine("⚠ Server task did not complete within timeout");
        }
        
        Console.WriteLine("BinaryMockPacketServer stopped.");
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

    public int GetUdpPort()
    {
        if (_udpClient?.Client.LocalEndPoint is IPEndPoint endPoint)
        {
            return endPoint.Port;
        }
        return -1;
    }

    private byte[] GenerateBinaryPacket()
    {
        return _entityType switch
        {
            "motion" => GenerateMotionPacket(),
            "safety" => GenerateSafetyPacket(),
            "onvif" => GenerateOnVifPacket(),
            _ => throw new InvalidOperationException($"Unknown entity type: {_entityType}")
        };
    }

    private byte[] GenerateMotionPacket()
    {
        // Generate a complete TCP packet with CapTrack PDU
        var packet = new List<byte>();
        
        // Ethernet header (14 bytes)
        packet.AddRange(new byte[] { 0x00, 0x11, 0x22, 0x33, 0x44, 0x55 }); // Dest MAC
        packet.AddRange(new byte[] { 0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB }); // Src MAC
        packet.AddRange(new byte[] { 0x08, 0x00 }); // EtherType (IPv4)
        
        // IPv4 header (20 bytes)
        packet.Add(0x45); // Version (4) + IHL (5)
        packet.Add(0x00); // TOS
        packet.AddRange(BitConverter.GetBytes((ushort)60).Reverse()); // Total Length (20 + 20 + 20 = 60)
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Identification
        packet.AddRange(new byte[] { 0x40, 0x00 }); // Flags + Fragment Offset
        packet.Add(0x40); // TTL
        packet.Add(0x06); // Protocol (TCP)
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Header Checksum
        packet.AddRange(new byte[] { 127, 0, 0, 1 }); // Source IP (loopback)
        packet.AddRange(new byte[] { 127, 0, 0, 1 }); // Destination IP (loopback)
        
        // TCP header (20 bytes)
        var srcPort = (ushort)_random.Next(1024, 65535);
        var dstPort = (ushort)4949; // Motion protocol port
        packet.AddRange(BitConverter.GetBytes(srcPort).Reverse()); // Source Port
        packet.AddRange(BitConverter.GetBytes(dstPort).Reverse()); // Destination Port
        packet.AddRange(new byte[] { 0x00, 0x00, 0x00, 0x00 }); // Sequence Number
        packet.AddRange(new byte[] { 0x00, 0x00, 0x00, 0x00 }); // Acknowledgment Number
        packet.Add(0x50); // Data Offset (5) + Reserved
        packet.Add(0x18); // Flags (PSH + ACK)
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Window Size
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Checksum
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Urgent Pointer
        
        // CapTrack PDU
        var opcodes = new ushort[] { 0x0101, 0x0102, 0x0103, 0x0104, 0x0105, 0x0106, 0x0107, 0x0108, 0x0109, 0x010A };
        var opcode = opcodes[_random.Next(opcodes.Length)];
        var axisId = (byte)_random.Next(0, 6);
        var groupId = (byte)_random.Next(1, 10);
        var floatValue = _random.NextSingle() * 100;
        
        // Convert float to bytes (little-endian)
        var floatBytes = BitConverter.GetBytes(floatValue);
        
        packet.AddRange(new byte[] { 0xCA, 0xFE }); // StartByte
        packet.Add((byte)(4 + floatBytes.Length)); // Length (GroupID + AxisID + OPCODE + DATA)
        packet.Add(groupId); // GroupID
        packet.Add(axisId); // AxisID
        packet.AddRange(BitConverter.GetBytes(opcode)); // OPCODE (little-endian)
        packet.AddRange(floatBytes); // DATA (float value)
        packet.Add((byte)_random.Next(0, 256)); // Checksum
        
        return packet.ToArray();
    }

    private byte[] GenerateSafetyPacket()
    {
        // Generate a complete UDP packet with Safety/Modbus-like PDU
        var packet = new List<byte>();
        
        // Ethernet header (14 bytes)
        packet.AddRange(new byte[] { 0x00, 0x11, 0x22, 0x33, 0x44, 0x55 }); // Dest MAC
        packet.AddRange(new byte[] { 0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB }); // Src MAC
        packet.AddRange(new byte[] { 0x08, 0x00 }); // EtherType (IPv4)
        
        // IPv4 header (20 bytes)
        packet.Add(0x45); // Version (4) + IHL (5)
        packet.Add(0x00); // TOS
        packet.AddRange(BitConverter.GetBytes((ushort)48).Reverse()); // Total Length (20 + 8 + 20 = 48)
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Identification
        packet.AddRange(new byte[] { 0x40, 0x00 }); // Flags + Fragment Offset
        packet.Add(0x40); // TTL
        packet.Add(0x11); // Protocol (UDP)
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Header Checksum
        packet.AddRange(new byte[] { 127, 0, 0, 1 }); // Source IP (loopback)
        packet.AddRange(new byte[] { 127, 0, 0, 1 }); // Destination IP (loopback)
        
        // UDP header (8 bytes)
        var srcPort = (ushort)_random.Next(1024, 65535);
        var dstPort = (ushort)502; // Modbus protocol port
        packet.AddRange(BitConverter.GetBytes(srcPort).Reverse()); // Source Port
        packet.AddRange(BitConverter.GetBytes(dstPort).Reverse()); // Destination Port
        packet.AddRange(BitConverter.GetBytes((ushort)20).Reverse()); // Length
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Checksum
        
        // Safety/Modbus-like PDU (20 bytes)
        packet.AddRange(new byte[] { 0x00, 0x01 }); // TID
        packet.AddRange(new byte[] { 0x00, 0x00 }); // PID
        packet.AddRange(new byte[] { 0x00, 0x0E }); // Length
        packet.Add(0x01); // UnitID
        packet.Add(0x06); // FunctionCode
        packet.AddRange(new byte[] { 0x00, 0x00 }); // param1
        packet.AddRange(new byte[] { 0x00, 0x00 }); // param2
        packet.AddRange(new byte[] { 0x00, 0x00 }); // param3
        packet.AddRange(new byte[] { 0x00, 0x00 }); // param4
        
        // DO and STATE codes
        var doCodes = new ushort[] { 0x0010, 0x0027, 0x0012, 0x0014 };
        var stateCodes = new ushort[] { 0x0000, 0xFF00, 0x0001, 0x0003 };
        
        var doCode = doCodes[_random.Next(doCodes.Length)];
        var stateCode = stateCodes[_random.Next(stateCodes.Length)];
        
        packet.AddRange(BitConverter.GetBytes(doCode).Reverse()); // DO (big-endian)
        packet.AddRange(BitConverter.GetBytes(stateCode).Reverse()); // STATE (big-endian)
        
        return packet.ToArray();
    }

    private byte[] GenerateOnVifPacket()
    {
        // Generate a complete HTTP packet with OnVIF binary data
        var packet = new List<byte>();
        
        // Generate binary body for OnVIF: [float zoom][float measurement]
        var zoom = _random.NextSingle() * 10f;
        var measurement = _random.NextSingle() * 1000f;
        var onvifData = new byte[8];
        BitConverter.GetBytes(zoom).CopyTo(onvifData, 0);
        BitConverter.GetBytes(measurement).CopyTo(onvifData, 4);
        
        // Create HTTP request
        var httpRequest = $"POST /onvif/device_service HTTP/1.1\r\n" +
                         $"Host: 127.0.0.1:8080\r\n" +
                         $"Content-Type: application/octet-stream\r\n" +
                         $"Content-Length: {onvifData.Length}\r\n" +
                         $"Connection: close\r\n" +
                         $"\r\n";
        var httpBytes = System.Text.Encoding.ASCII.GetBytes(httpRequest);
        var totalLength = 20 + 20 + httpBytes.Length + onvifData.Length; // IP + TCP + HTTP + data
        
        // Ethernet header (14 bytes)
        packet.AddRange(new byte[] { 0x00, 0x11, 0x22, 0x33, 0x44, 0x55 }); // Dest MAC
        packet.AddRange(new byte[] { 0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB }); // Src MAC
        packet.AddRange(new byte[] { 0x08, 0x00 }); // EtherType (IPv4)
        
        // IPv4 header (20 bytes)
        packet.Add(0x45); // Version (4) + IHL (5)
        packet.Add(0x00); // TOS
        packet.AddRange(BitConverter.GetBytes((ushort)totalLength).Reverse()); // Total Length
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Identification
        packet.AddRange(new byte[] { 0x40, 0x00 }); // Flags + Fragment Offset
        packet.Add(0x40); // TTL
        packet.Add(0x06); // Protocol (TCP)
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Header Checksum
        packet.AddRange(new byte[] { 127, 0, 0, 1 }); // Source IP (loopback)
        packet.AddRange(new byte[] { 127, 0, 0, 1 }); // Destination IP (loopback)
        
        // TCP header (20 bytes)
        var srcPort = (ushort)_random.Next(1024, 65535);
        var dstPort = (ushort)8080; // HTTP port
        packet.AddRange(BitConverter.GetBytes(srcPort).Reverse()); // Source Port
        packet.AddRange(BitConverter.GetBytes(dstPort).Reverse()); // Destination Port
        packet.AddRange(new byte[] { 0x00, 0x00, 0x00, 0x00 }); // Sequence Number
        packet.AddRange(new byte[] { 0x00, 0x00, 0x00, 0x00 }); // Acknowledgment Number
        packet.Add(0x50); // Data Offset (5) + Reserved
        packet.Add(0x18); // Flags (PSH + ACK)
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Window Size
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Checksum
        packet.AddRange(new byte[] { 0x00, 0x00 }); // Urgent Pointer
        
        // HTTP request
        packet.AddRange(httpBytes);
        
        // OnVIF binary data
        packet.AddRange(onvifData);
        
        return packet.ToArray();
    }

    public void Dispose()
    {
        Stop();
        _cancellationTokenSource?.Dispose();
    }
}
