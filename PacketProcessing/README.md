# Packet Processing Service

A consolidated .NET 8 service that provides complete packet capture, processing, and storage functionality using SharpPcap and QuestDB.

## Architecture Overview

The service implements the complete flow you specified:

1. **Packet Capture Workers** - Intercept packets using SharpPcap from all network interfaces
2. **Channel-based Communication** - Async channels for packet transmission between workers
3. **QuestDB Storage Workers** - Process packets in batches and store them in QuestDB
4. **30ms Batch Processing** - Packets are processed every 30ms with configurable batch sizes
5. **WebSocket Transmission** - Last packet from each batch is transmitted via WebSocket (placeholder implementation)

## Project Structure

```
PacketProcessing/
├── Models/
│   └── PacketData.cs          # Packet data model
├── Interfaces/
│   └── IPacketStorage.cs       # Storage interface
├── Configuration/
│   └── QuestDbOptions.cs      # QuestDB connection settings
├── Services/
│   ├── QuestDbPacketStorage.cs # Main storage service with batching
│   └── PacketCaptureWorker.cs  # SharpPcap-based packet capture
├── Program.cs                   # Main application entry point
├── appsettings.json            # Configuration
└── PacketProcessing.csproj     # Project file
```

## Features

- **Multi-device Capture**: Automatically detects and captures from all available network interfaces
- **Configurable Filtering**: BPF filters for specific protocols and ports
- **Batch Processing**: Configurable batch sizes and timeouts (default: 1000 packets, 30ms)
- **QuestDB Integration**: High-performance time-series database for packet storage
- **Async Processing**: Non-blocking packet processing using channels
- **Structured Logging**: Comprehensive logging with configurable levels
- **Health Monitoring**: Built-in health checks and monitoring

## Prerequisites

- .NET 8.0 SDK
- Docker and Docker Compose (for QuestDB)
- libpcap/Npcap (for packet capture)

## Quick Start

### 1. Start QuestDB

```bash
docker-compose up -d questdb
```

QuestDB will be available at:
- Web Console: http://localhost:8812
- PostgreSQL: localhost:9009
- InfluxDB: localhost:9000

### 2. Build and Run

```bash
cd PacketProcessing
dotnet build
dotnet run
```

### 3. Test with UDP Blaster

Use the existing `udp_blaster.py` script to generate test traffic:

```bash
python3 udp_blaster.py 5000 1000
```

## Configuration

### QuestDB Settings (`appsettings.json`)

```json
{
  "QuestDB": {
    "Host": "localhost",
    "Port": 8812,
    "Username": "quest",
    "Password": "quest",
    "Database": "qdb",
    "BatchSize": 1000,
    "BatchTimeoutMs": 30
  }
}
```

### Packet Capture Settings

```json
{
  "PacketCapture": {
    "Filter": "udp",
    "Port": 5000
  }
}
```

## Database Schema

The service automatically creates the following table in QuestDB:

```sql
CREATE TABLE packets (
    id SYMBOL,
    timestamp TIMESTAMP,
    source_ip SYMBOL,
    destination_ip SYMBOL,
    source_port INT,
    destination_port INT,
    length INT,
    protocol SYMBOL,
    payload STRING,
    device_name SYMBOL
) TIMESTAMP(timestamp) PARTITION BY DAY;
```

## Performance Characteristics

- **Batch Processing**: 1000 packets per batch (configurable)
- **Processing Interval**: 30ms (configurable)
- **Storage**: Time-series optimized with daily partitioning
- **Concurrency**: Async processing with channel-based communication
- **Memory**: Efficient buffering with automatic cleanup

## Monitoring and Logging

The service provides comprehensive logging:

- **Packet Counts**: Real-time packet processing statistics
- **Batch Performance**: Batch processing timing and success rates
- **Error Handling**: Detailed error logging with context
- **Health Metrics**: System health and performance indicators

## WebSocket Integration

The service includes a placeholder for WebSocket transmission of the last packet from each batch. To implement:

1. Add WebSocket server package (e.g., `System.Net.WebSockets.Server`)
2. Implement `SendPacketViaWebSocketAsync` method in `QuestDbPacketStorage`
3. Configure WebSocket endpoints and authentication

## Troubleshooting

### Common Issues

1. **No capture devices found**: Install libpcap/Npcap
2. **QuestDB connection failed**: Ensure Docker container is running
3. **Permission denied**: Run with appropriate network capture privileges
4. **High memory usage**: Adjust batch sizes and processing intervals

### Performance Tuning

- **Batch Size**: Increase for higher throughput, decrease for lower latency
- **Processing Interval**: Adjust based on real-time requirements
- **Buffer Sizes**: Configure based on available memory
- **Device Filters**: Use specific BPF filters to reduce processing load

## Development

### Adding New Features

1. **New Packet Types**: Extend `PacketData` model
2. **Additional Storage**: Implement `IPacketStorage` interface
3. **Custom Filters**: Modify `PacketCaptureWorker` filter logic
4. **Analytics**: Add new QuestDB queries and endpoints

### Testing

- **Unit Tests**: Test individual components
- **Integration Tests**: Test QuestDB integration
- **Performance Tests**: Load testing with high packet volumes
- **Network Tests**: Test with various network conditions

## License

This project is part of the kanat_server solution.
