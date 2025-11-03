# Kanat Packet Processing System

A high-performance, real-time telemetry ingestion and analysis system built with .NET 8, QuestDB, PostgreSQL, and SignalR. The system captures network packets from multiple sources, processes them in real-time, and provides a web-based dashboard for monitoring and analysis.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the System](#running-the-system)
- [Dashboard](#dashboard)
- [API Reference](#api-reference)
- [SignalR Hub](#signalr-hub)
- [Database Schema](#database-schema)
- [Development](#development)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

---

## Features

### Core Capabilities

- **Multi-Source Packet Capture**: Capture packets from Motion, Safety, OnVIF, and Weather sources over TCP/UDP
- **Real-Time Processing**: High-throughput packet processing with configurable worker pools (2-8 workers)
- **QuestDB Integration**: Time-series database optimized for 6000+ packets per second with WAL enabled
- **Session Management**: Create, manage, and archive range sessions with automatic table partitioning
- **Web Dashboard**: Real-time telemetry visualization with live charts and statistics
- **SignalR Streaming**: Push packet data to connected clients in real-time with configurable sampling intervals
- **Playback Mode**: Replay historical data at configurable speeds

### Performance

- **Throughput**: Sustains 6000+ rows per second without stalling
- **Latency**: Sub-100ms packet-to-storage latency
- **Scalability**: Configurable worker pools and batch processing
- **Efficient Storage**: WAL-enabled QuestDB tables with daily partitioning

---

## Architecture

### System Components

```
┌─────────────────┐
│  Network Device │
│   (eth0, etc.)  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│              HandlerService                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │  Motion  │  │  Safety  │  │  OnVIF   │             │
│  │  Handler │  │  Handler │  │  Handler │             │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘             │
└────────┼─────────────┼──────────────┼──────────────────┘
         │             │              │
         ▼             ▼              ▼
    ┌─────────────────────────────────────────┐
    │        Channels (High-Capacity)         │
    │  Motion: 1M | Safety: 1M | OnVIF: 100K │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │        DbWriterService (ILP)            │
    │  Workers: 2-8 | Batch: 2000 | 1000ms   │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                    QuestDB                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │  motion_packets   (WAL, PARTITION BY DAY)       │   │
│  │  safety_packets   (WAL, PARTITION BY DAY)       │   │
│  │  onvif_packets    (WAL, PARTITION BY DAY)       │   │
│  │  motion_packets_{rangeId} (Session Tables)      │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                TelemetryBroadcaster                     │
│          (Push stats to SignalR clients)                │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │    SignalR Hub        │
         │  /hubs/packets        │
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  Web Dashboard        │
         │  (Real-time Charts)   │
         └───────────────────────┘
```

### Database Architecture

**PostgreSQL** (Range Entities):
- Stores range metadata, events, hits, targets
- Used for session management and historical queries
- Connection: Port 5432

**QuestDB** (Packet Entities):
- Time-series database for high-frequency packet data
- WAL-enabled with daily partitioning
- ILP ingestion on Port 9000, PostgreSQL wire protocol on 8812, HTTP on 9009
- Indexed subscription keys for fast filtering

---

## Prerequisites

### Required Software

- **.NET 8 SDK** or later
- **Docker** and **Docker Compose** (for database containers)
- **Linux** or **macOS** (for packet capture)
- **Windows** users should use WSL2

### Network Access

- Permission to capture packets on network interfaces
- Access to target packet sources (configure IPs/ports in `appsettings.json`)

---

## Installation

### 1. Clone Repository

```bash
git clone <repository-url>
cd KanatBackend
```

### 2. Start Databases with Docker

```bash
# Start PostgreSQL and QuestDB
docker-compose -f docker-compose.dev.yml up -d

# Or for production
docker-compose -f docker-compose.prod.yml up -d
```

### 3. Configure Application

Edit `PacketProcessing/appsettings.Development.json` or `appsettings.Production.json`:

```json
{
  "Application": {
    "Url": "http://0.0.0.0:10901"
  },
  "Postgres": {
    "Host": "localhost",
    "Port": 5432,
    "Database": "RangeDBDev",
    "Username": "postgres",
    "Password": "postgres"
  },
  "QuestDb": {
    "Host": "localhost",
    "PostgresPort": 8812,
    "InfluxPort": 9000,
    "HttpPort": 9009,
    "Username": "quest",
    "Password": "quest",
    "Database": "PacketDBDev"
  }
}
```

### 4. Build and Run

```bash
cd PacketProcessing
dotnet restore
dotnet build
dotnet run --environment Development
```

---

## Configuration

### Application Configuration

Location: `PacketProcessing/appsettings.json`

#### Concurrency Settings

```json
{
  "Concurrency": {
    "SingleReader": false,
    "SingleWriter": false,
    "MinWorkers": 2,
    "MaxWorkers": 4,
    "BatchSize": 2000,
    "BatchTimeoutMs": 1000
  }
}
```

- **MinWorkers / MaxWorkers**: Number of worker threads for packet processing (2-8)
- **BatchSize**: Rows to buffer before flushing to QuestDB (default: 2000)
- **BatchTimeoutMs**: Maximum time to wait before flushing incomplete batches

#### Data Pipe Configuration

Configure each packet source:

```json
{
  "DataPipes": {
    "MotionCapture": {
      "Network": {
        "Device": "any",
        "Protocol": "tcp",
        "IPs": ["132.8.7.125"],
        "Ports": []  // Optional, empty means all ports
      },
      "Channel": {
        "Members": 1000000  // Channel capacity
      },
      "Sampling": {
        "IntervalMs": 30
      }
    }
  }
}
```

- **Device**: Network interface name or "any" for all interfaces
- **Protocol**: "tcp" or "udp"
- **IPs**: Array of source IP addresses to filter
- **Ports**: Array of ports to filter (optional, empty = all)
- **Members**: Channel capacity (buffer size)
- **IntervalMs**: Sampling interval for metrics

---

## Running the System

### Development Mode

```bash
cd PacketProcessing
dotnet run --environment Development
```

Dashboard available at: http://localhost:10901

### Production Mode

```bash
dotnet publish -c Release -o ./publish
cd publish
dotnet PacketProcessing.dll --environment Production
```

Dashboard available at: http://localhost:10900

### Using Docker

```bash
docker build -t kanat-backend .
docker run -p 10901:10901 kanat-backend
```

---

## Dashboard

### Accessing the Dashboard

Open your browser to:
- **Development**: http://localhost:10901
- **Production**: http://localhost:10900

### Features

1. **Mode Selector**: Switch between Realtime and Playback modes
2. **Range Management**: Create and manage packet capture sessions
3. **Live Telemetry**: Real-time charts showing:
   - Packets Per Second (PPS)
   - Channel Utilization
   - Latency metrics
4. **Stream Registration**: Register for specific packet streams with optional sampling intervals
5. **Console Access**: Quick links to:
   - Swagger API documentation
   - QuestDB console
   - Seq log viewer

### Telemetry Dashboard Sections

- **THROUGHPUT (Last 60 seconds)**: Live PPS chart for all packet types
- **Channel Utilization Tables**: Real-time buffer usage per packet type
- **Stream Management**: Add/remove packet streams dynamically with configurable sampling intervals

---

## API Reference

### Base URL

- **Development**: `http://localhost:10901/api/range`
- **Production**: `http://localhost:10900/api/range`

### Authentication

Currently none (configure as needed for production).

### Mode Management

#### Get Current Mode

```http
GET /api/range/mode
```

**Response:**
```json
{
  "success": true,
  "data": "Realtime",
  "statusCode": 200
}
```

#### Change Mode

```http
PUT /api/range/mode/{mode}
```

**Parameters:**
- `mode`: `Realtime` or `Playback`

---

### Realtime Operations

#### Start Realtime Capture

```http
POST /api/range/realtime/start
Content-Type: application/json

{
  "description": "My Range Session",
  "config": {
    "bpfConfig": {
      "device": "eth0",
      "motion": [{ "ip": "132.8.7.125", "port": 1234 }],
      "safety": [{ "ip": "132.8.7.101", "port": 5678 }],
      "onvif": [{ "ip": "132.8.7.121", "port": 8080 }]
    },
    "mtxConfig": {
      "ip": "127.0.0.1",
      "port": 8554
    }
  }
}
```

#### Stop Capture

```http
DELETE /api/range/realtime/stop
```

#### Get Available Devices

```http
GET /api/range/realtime/devices
```

**Response:**
```json
{
  "success": true,
  "data": ["eth0", "wlan0", "lo"]
}
```

#### Reset Statistics

```http
POST /api/range/reset
```

---

### Range Management

#### Get All Ranges (Paginated)

```http
GET /api/range/ranges?page=1&pageSize=10
```

#### Get Range by ID

```http
GET /api/range/ranges/{id}
```

#### Create Range

```http
POST /api/range/ranges
Content-Type: application/json

{
  "description": "Test Range",
  "startTime": 1642248600000,
  "endTime": 1642248660000
}
```

#### Update Range

```http
PUT /api/range/ranges/{id}
Content-Type: application/json

{
  "description": "Updated Range",
  "startTime": 1642248600000,
  "endTime": 1642248660000
}
```

#### Delete Range

```http
DELETE /api/range/ranges/{id}
```

#### Clear Packets

```http
DELETE /api/range/packets/clear
```

Note: This truncates ALL base tables regardless of time range.

---

### Playback Operations

#### Set Playback Pace

```http
PUT /api/range/playback/pace/{pace}
```

**Parameters:**
- `pace`: Speed multiplier (1.0 = normal, 2.0 = double)

---

## SignalR Hub

### Connection

```javascript
const connection = new signalR.HubConnectionBuilder()
    .withUrl("http://localhost:10901/hubs/packets")
    .build();

await connection.start();
```

### Hub Methods

#### Register to Stream

```javascript
await connection.invoke("RegisterToMethod", {
    dataPipe: "Motion",
    description: "MOT_GetMotorCurrent",
    isCmd: false,
    axis: 1
});
```

#### Unregister from Stream

```javascript
await connection.invoke("UnregisterFromMethod", "motion|mot_getmotorcurrent|false|1");
```

#### Set Sampling Interval

Configure packet sampling interval to reduce transmission frequency:

```javascript
await connection.invoke("SetTimeInterval", {
    subscriptionKey: "motion|mot_getmotorcurrent|false|1",
    intervalMs: 100  // Transmit only every 100ms
});
```

**Notes:**
- Setting `intervalMs` to 0 or omitting it results in **no sampling** (all packets transmitted)
- Intervals are per-stream; each subscription key has its own timer
- Timers reset automatically after each transmission
- Packets arriving before the interval elapses are discarded

### Client Events

#### OnReceivePacket

```javascript
connection.on("OnReceivePacket", (data) => {
    console.log("Packet:", data.subscriptionKey, data.value, data.timestamp);
});
```

#### Ack

```javascript
connection.on("Ack", (ack) => {
    console.log("Operation:", ack.operationType, ack.success);
});
```

---

## Database Schema

### QuestDB Tables

#### motion_packets

```sql
CREATE TABLE motion_packets (
    timestamp   TIMESTAMP,
    id          SYMBOL CAPACITY 256 CACHE,
    isCmd       BOOLEAN,
    opCode      STRING,
    description STRING,
    axis        INT,
    value       DOUBLE
) TIMESTAMP(timestamp) PARTITION BY DAY WAL;

ALTER TABLE motion_packets ALTER COLUMN id ADD INDEX;
```

#### safety_packets

```sql
CREATE TABLE safety_packets (
    timestamp   TIMESTAMP,
    id          SYMBOL CAPACITY 256 CACHE,
    name        STRING,
    isCmd       BOOLEAN,
    opCode      STRING,
    description STRING,
    state       STRING
) TIMESTAMP(timestamp) PARTITION BY DAY WAL;

ALTER TABLE safety_packets ALTER COLUMN id ADD INDEX;
```

#### onvif_packets

```sql
CREATE TABLE onvif_packets (
    timestamp    TIMESTAMP,
    id           SYMBOL CAPACITY 256 CACHE,
    isCmd        BOOLEAN,
    description  STRING,
    zoom         DOUBLE,
    measurement  DOUBLE
) TIMESTAMP(timestamp) PARTITION BY DAY WAL;

ALTER TABLE onvif_packets ALTER COLUMN id ADD INDEX;
```

### PostgreSQL Tables

See `PacketProcessing/src/Context/PostgresDbContext.cs` for Entity Framework models:
- RangeEntity
- EventEntity
- HitEntity
- TargetEntity

---

## Development

### Project Structure

```
PacketProcessing/
├── src/
│   ├── Controllers/        # API endpoints
│   ├── Services/           # Business logic
│   │   ├── Realtime/       # Capture and processing
│   │   ├── Playback/       # Historical playback
│   │   └── Transmission/   # SignalR broadcasting
│   ├── Repositories/       # Data access
│   ├── Entities/           # Domain models
│   ├── DTOs/              # Data transfer objects
│   ├── Config/            # Configuration classes
│   ├── Context/           # EF Core and QuestDB contexts
│   ├── Hubs/              # SignalR hub
│   ├── Telemetry/         # Metrics collection
│   └── Utils/             # Utilities and parsers
├── tests/                 # Unit and integration tests
├── wwwroot/              # Web dashboard
└── appsettings.json      # Configuration
```

### Running Tests

```bash
# All tests
dotnet test

# Unit tests only
dotnet test --filter "Category=Unit"

# Integration tests only
dotnet test --filter "Category=Integration"

# Specific test
dotnet test --filter "FullyQualifiedName~TestName"
```

### Code Style

- Use `Async` suffix for async methods
- Use dependency injection for all services
- Follow repository pattern for data access
- Use structured logging with Serilog

---

## Testing

### Unit Tests

- Repository tests with Moq
- Service tests with mocked dependencies
- Hub tests for SignalR logic

### Integration Tests

- Full HTTP API testing
- Database integration
- End-to-end workflows

### Manual Testing

1. **Start Development Environment**:
   ```bash
   dotnet run --environment Development
   ```

2. **Access Dashboard**: http://localhost:10901

3. **Start Capture**: Use dashboard or API

4. **Monitor Telemetry**: Watch charts update in real-time

5. **Check Databases**:
   - PostgreSQL: Use pgAdmin or `psql`
   - QuestDB: http://localhost:9009

---

## Troubleshooting

### Common Issues

#### Port Already in Use

```bash
# Find process using port
lsof -i :10901

# Kill process
kill -9 <PID>
```

#### Permission Denied for Packet Capture

```bash
# Linux: Grant capabilities
sudo setcap cap_net_raw,cap_net_admin=eip /path/to/PacketProcessing

# Or run with sudo (not recommended)
sudo dotnet run
```

#### Database Connection Failed

- Verify Docker containers are running: `docker ps`
- Check connection strings in `appsettings.json`
- Review logs for connection errors

#### No Packets Received

- Verify network device is correct
- Check IP/port filters in configuration
- Ensure source is sending packets
- Review logs for filtering details

### Logs

Logs are written to console and can be viewed via:
- Dashboard console buttons
- Seq (if configured)
- Standard output/error streams

### Performance Tuning

1. **Increase Workers**: Set `MaxWorkers` to 4-8
2. **Adjust Batching**: Increase `BatchSize` to 5000 for high-throughput
3. **Channel Capacity**: Ensure sufficient buffer size
4. **QuestDB Settings**: Tune WAL and partition settings
5. **SignalR Sampling**: Use `SetTimeInterval` to reduce packet transmission frequency on high-rate streams

---

## Additional Resources

- [QuestDB Documentation](https://questdb.io/docs/)
- [SignalR Documentation](https://docs.microsoft.com/en-us/aspnet/core/signalr/)
- [.NET Documentation](https://docs.microsoft.com/en-us/dotnet/)
- [SharpPcap Documentation](https://github.com/chmorgan/sharppcap)

---

## License

[Specify license]

## Support

For issues, questions, or contributions, please contact [your team/email] or open an issue in the repository.
