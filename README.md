# Kanat Packet Processing System

A real-time system for monitoring packets over shared LAN, storing them, and passing them to analysis over time.

## Table of Contents

- [DTOs (Data Transfer Objects)](#dtos-data-transfer-objects)
- [REST API Endpoints](#rest-api-endpoints)
- [SignalR Hub](#signalr-hub)
- [Examples](#examples)

---

## DTOs (Data Transfer Objects)

### Core DTOs

#### `ResponseResult<T>` / `ResponseResult`
Generic response wrapper for all API operations.

```csharp
public class ResponseResult<T>
{
    public bool Success { get; set; }
    public T? Data { get; set; }
    public string? ErrorMessage { get; set; }
    public int StatusCode { get; set; }
    public DateTime Timestamp { get; set; }
}
```

#### `PaginatedResult<T>`
Generic paginated result for API operations that return paginated data.

```csharp
public class PaginatedResult<T>
{
    public IEnumerable<T> Items { get; set; }
    public int Page { get; set; }
    public int PageSize { get; set; }
    public int TotalCount { get; set; }
    public int TotalPages { get; set; }
    public bool HasPreviousPage { get; set; }
    public bool HasNextPage { get; set; }
    public DateTime Timestamp { get; set; }
}
```

### Stream DTOs

#### `StreamRequestDto`
Stream request for packet transmission.

```csharp
public sealed class StreamRequestDto
{
    public required DataPipes DataPipe { get; init; }
    public required string Description { get; init; }
    public bool? IsCmd { get; init; } = false;
    public int? Axis { get; init; } = 0;
    public string SubscriptionKey { get; } // Auto-generated
}
```

### Packet DTOs

#### `MotionPacketDto`
Data Transfer Object for MotionPacketEntity.

```csharp
public class MotionPacketDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public bool IsCmd { get; set; }
    public string OpCode { get; set; }
    public string Description { get; set; }
    public int Axis { get; set; }
    public double? Value { get; set; }
}
```

#### `SafetyPacketDto`
Data Transfer Object for SafetyPacketEntity.

```csharp
public class SafetyPacketDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public string Name { get; set; }
    public bool IsCmd { get; set; }
    public string OpCode { get; set; }
    public string Description { get; set; }
    public string State { get; set; }
}
```

#### `OnVIFPacketDto`
Data Transfer Object for OnVIFPacketEntity.

```csharp
public class OnVIFPacketDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public bool IsCmd { get; set; }
    public string Description { get; set; }
    public double? Zoom { get; set; }
    public double? Measurement { get; set; }
}
```

### Range DTOs

#### `RangeDto`
Data Transfer Object for RangeEntity.

```csharp
public class RangeDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public long Start { get; set; }
    public long End { get; set; }
    public string Description { get; set; }
}
```

#### `EventDto`
Data Transfer Object for EventEntity.

```csharp
public class EventDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public long Start { get; set; }
    public long End { get; set; }
    public Guid RangeId { get; set; }
}
```

#### `HitDto`
Data Transfer Object for HitEntity.

```csharp
public class HitDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public float RangeToTarget { get; set; }
    public int PosX { get; set; }
    public int PosY { get; set; }
    public int CenterX { get; set; }
    public int CenterY { get; set; }
    public Guid TargetId { get; set; }
    public Guid EventId { get; set; }
}
```

#### `TargetDto`
Data Transfer Object for TargetEntity.

```csharp
public class TargetDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public int PosX { get; set; }
    public int PosY { get; set; }
    public int CenterX { get; set; }
    public int CenterY { get; set; }
}
```

### SignalR DTOs

#### `AckDto`
Acknowledgement DTO for SignalR operations.

```csharp
public class AckDto
{
    public required OperationType OperationType { get; init; }
    public required bool Success { get; init; }
    public object? Message { get; init; }
}
```

### Utility DTOs

#### `PlainDataDto`
Plain data DTO for telemetry.

```csharp
public class PlainDataDto
{
    public long Timestamp { get; set; }
    public double Value { get; set; }
    public DataPipes DataPipe { get; set; }
    public string MethodName { get; set; }
}
```

#### `DeviceSubscriptionStatusDto`
Device subscription status DTO.

```csharp
public class DeviceSubscriptionStatusDto
{
    public string DeviceName { get; set; }
    public string Filter { get; set; }
    public bool IsCapturing { get; set; }
}
```

### Enums

#### `DataPipes`
Data pipe types for packet processing.

```csharp
public enum DataPipes
{
    Motion,
    OnVIF,
    Safety
}
```

#### `States`
Application states.

```csharp
public enum States
{
    Realtime,
    Playback
}
```

#### `OperationType`
SignalR operation types.

```csharp
public enum OperationType
{
    RegisterToMethod,
    UnregisterFromMethod,
    ConnectionEstablished,
    ConnectionClosed
}
```

---

## REST API Endpoints

Base URL: `http://localhost:10901/api/v1/range`

### Mode Management

#### Change Application Mode
```http
PUT /api/v1/range/mode/{mode}
```

**Parameters:**
- `mode` (path): `Realtime` or `Playback`

**Returns:** `ResponseResult`

**Example:**
```bash
curl -X PUT "http://localhost:10901/api/v1/range/mode/Realtime"
```

**Response:**
```json
{
  "success": true,
  "data": null,
  "errorMessage": null,
  "statusCode": 200,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### Get Current Mode
```http
GET /api/v1/range/mode
```

**Returns:** `ResponseResult<string>`

**Example:**
```bash
curl "http://localhost:10901/api/v1/range/mode"
```

**Response:**
```json
{
  "success": true,
  "data": "Realtime",
  "errorMessage": null,
  "statusCode": 200,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Realtime Operations

#### Start All Services
```http
POST /api/v1/range/realtime/start/{deviceName}
```

**Parameters:**
- `deviceName` (path): Network device name

**Returns:** `ResponseResult`

**Example:**
```bash
curl -X POST "http://localhost:10901/api/v1/range/realtime/start/eth0"
```

#### Stop All Services
```http
DELETE /api/v1/range/realtime/stop
```

**Returns:** `ResponseResult`

**Example:**
```bash
curl -X DELETE "http://localhost:10901/api/v1/range/realtime/stop"
```

#### Get Available Devices
```http
GET /api/v1/range/realtime/devices
```

**Returns:** `ResponseResult<ICollection<string>>`

**Example:**
```bash
curl "http://localhost:10901/api/v1/range/realtime/devices"
```

**Response:**
```json
{
  "success": true,
  "data": ["eth0", "wlan0", "lo"],
  "errorMessage": null,
  "statusCode": 200,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### Reset Statistics
```http
POST /api/v1/range/reset
```

**Returns:** `ResponseResult`

**Example:**
```bash
curl -X POST "http://localhost:10901/api/v1/range/reset"
```

### Playback Operations

#### Set Playback Pace
```http
PUT /api/v1/range/playback/pace/{pace}
```

**Parameters:**
- `pace` (path): Playback speed multiplier (e.g., 1.0 = normal, 2.0 = double speed)

**Returns:** `ResponseResult`

**Example:**
```bash
curl -X PUT "http://localhost:10901/api/v1/range/playback/pace/2.0"
```

### Range Entity Management

#### Get Range by ID
```http
GET /api/v1/range/ranges/{id}
```

**Parameters:**
- `id` (path): Range GUID

**Returns:** `ResponseResult<RangeDto>`

**Example:**
```bash
curl "http://localhost:10901/api/v1/range/ranges/123e4567-e89b-12d3-a456-426614174000"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "timestamp": "2024-01-15T10:30:00Z",
    "start": 1642248600000,
    "end": 1642248660000,
    "description": "Test Range Session"
  },
  "errorMessage": null,
  "statusCode": 200,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### Create Range
```http
POST /api/v1/range/ranges
```

**Body:** `RangeDto`

**Returns:** `ResponseResult<RangeDto>`

**Example:**
```bash
curl -X POST "http://localhost:10901/api/v1/range/ranges" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2024-01-15T10:30:00Z",
    "start": 1642248600000,
    "end": 1642248660000,
    "description": "New Range Session"
  }'
```

#### Get All Ranges (Paginated)
```http
GET /api/v1/range/ranges?page=1&pageSize=100
```

**Parameters:**
- `page` (query): Page number (default: 1)
- `pageSize` (query): Items per page (default: 1000)

**Returns:** `ResponseResult<PaginatedResult<RangeDto>>`

**Example:**
```bash
curl "http://localhost:10901/api/v1/range/ranges?page=1&pageSize=10"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "timestamp": "2024-01-15T10:30:00Z",
        "start": 1642248600000,
        "end": 1642248660000,
        "description": "Test Range Session"
      }
    ],
    "page": 1,
    "pageSize": 10,
    "totalCount": 1,
    "totalPages": 1,
    "hasPreviousPage": false,
    "hasNextPage": false,
    "timestamp": "2024-01-15T10:30:00Z"
  },
  "errorMessage": null,
  "statusCode": 200,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### Update Range
```http
PUT /api/v1/range/ranges/{id}
```

**Parameters:**
- `id` (path): Range GUID

**Body:** `RangeDto`

**Returns:** `ResponseResult<RangeDto>`

**Example:**
```bash
curl -X PUT "http://localhost:10901/api/v1/range/ranges/123e4567-e89b-12d3-a456-426614174000" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2024-01-15T10:30:00Z",
    "start": 1642248600000,
    "end": 1642248660000,
    "description": "Updated Range Session"
  }'
```

#### Delete Range
```http
DELETE /api/v1/range/ranges/{id}
```

**Parameters:**
- `id` (path): Range GUID

**Returns:** `ResponseResult`

**Example:**
```bash
curl -X DELETE "http://localhost:10901/api/v1/range/ranges/123e4567-e89b-12d3-a456-426614174000"
```

#### Clear Packets
```http
DELETE /api/v1/range/packets/clear?start=2024-01-15T10:00:00Z&end=2024-01-15T11:00:00Z
```

**Parameters:**
- `start` (query): Start timestamp (ISO-8601)
- `end` (query): End timestamp (ISO-8601)

**Returns:** `ResponseResult<string>`

**Example:**
```bash
curl -X DELETE "http://localhost:10901/api/v1/range/packets/clear?start=2024-01-15T10:00:00Z&end=2024-01-15T11:00:00Z"
```

### Development Endpoints

#### Get All Ranges (Development Only)
```http
GET /api/v1/range/dev/ranges/all
```

**Returns:** `ResponseResult<IEnumerable<RangeDto>>`

#### Delete All Ranges (Development Only)
```http
DELETE /api/v1/range/dev/ranges/all
```

**Returns:** `ResponseResult<int>` (count of deleted ranges)

---

## SignalR Hub

**Hub URL:** `http://localhost:10901/hubs/packets`

### Connection Events

#### OnConnectedAsync
Automatically called when a client connects.

**Returns:** Array of `AckDto` with previously registered streams.

**Example Response:**
```json
[
  {
    "operationType": "ConnectionEstablished",
    "success": true,
    "message": "motion|mot_getmotorcurrent|false|1"
  },
  {
    "operationType": "ConnectionEstablished", 
    "success": true,
    "message": "safety|do3_fire1|true|"
  }
]
```

#### OnDisconnectedAsync
Automatically called when a client disconnects.

**Returns:** `AckDto` with connection closed status.

**Example Response:**
```json
{
  "operationType": "ConnectionClosed",
  "success": true,
  "message": null
}
```

### Hub Methods

#### RegisterToMethod
Register to receive packets for a specific stream.

**Parameters:** `StreamRequestDto`

**Returns:** `AckDto`

**Example:**
```javascript
// JavaScript client
const streamRequest = {
  dataPipe: "Motion",
  description: "MOT_GetMotorCurrent",
  isCmd: false,
  axis: 1
};

await connection.invoke("RegisterToMethod", streamRequest);
```

**Response:**
```json
{
  "operationType": "RegisterToMethod",
  "success": true,
  "message": {
    "dataPipe": "Motion",
    "description": "MOT_GetMotorCurrent",
    "isCmd": false,
    "axis": 1,
    "subscriptionKey": "motion|mot_getmotorcurrent|false|1"
  }
}
```

#### UnregisterFromMethod
Unregister from receiving packets for a specific stream.

**Parameters:** `string subscriptionKey`

**Returns:** `AckDto`

**Example:**
```javascript
// JavaScript client
const streamRequest = {
  dataPipe: "Motion",
  description: "MOT_GetMotorCurrent", 
  isCmd: false,
  axis: 1
};

// Build subscription key exactly like the server and lowercase it
const subscriptionKey = `${streamRequest.dataPipe}|${streamRequest.description}|${streamRequest.isCmd ?? false}|${streamRequest.axis ?? ""}`.toLowerCase();

await connection.invoke("UnregisterFromMethod", subscriptionKey);
```

**Response:**
```json
{
  "operationType": "UnregisterFromMethod",
  "success": true,
  "message": "motion|mot_getmotorcurrent|false|1"
}
```

### Client Events

#### Ack
Received when operations complete.

**Parameters:** `AckDto` or `AckDto[]`

**Example:**
```javascript
// JavaScript client
connection.on("Ack", (ackData) => {
  if (Array.isArray(ackData)) {
    // Multiple ACKs (on connect)
    ackData.forEach(ack => {
      console.log(`ACK Received: ${JSON.stringify(ack)}`);
    });
  } else {
    // Single ACK (on register/unregister/disconnect)
    console.log(`ACK Received: ${JSON.stringify(ackData)}`);
  }
});
```

#### OnReceivePacket
Received when packet data is transmitted.

**Parameters:** `PlainDataDto`

Plain payload from server:

```json
{
  "subscriptionKey": "motion|mot_getmotorcurrent|false|1",
  "timestamp": 1730093700000,
  "value": 42.5
}
```

**Example:**
```javascript
// JavaScript client
connection.on("OnReceivePacket", (plainData) => {
  console.log("Packet Received:", plainData);
  // plainData.subscriptionKey, plainData.timestamp (ms), plainData.value
});
```

---

## Examples

### Complete JavaScript Client Example

```javascript
// SignalR connection setup
const connection = new signalR.HubConnectionBuilder()
    .withUrl("http://localhost:10901/hubs/packets")
    .withAutomaticReconnect([0, 1000, 2000, 5000])
    .build();

// Connection event handlers
connection.onclose((error) => {
    console.log("Connection closed:", error);
});

connection.onreconnecting((error) => {
    console.log("Reconnecting...");
});

connection.onreconnected((connectionId) => {
    console.log("Reconnected successfully");
});

// ACK handler
connection.on("Ack", (ackData) => {
    if (Array.isArray(ackData)) {
        console.log("Multiple ACKs received:", ackData);
    } else {
        console.log("Single ACK received:", ackData);
    }
});

// Packet data handler
connection.on("OnReceivePacket", (packetData) => {
    console.log("Packet received:", packetData);
    
    // Process different packet types
    switch (packetData.dataPipe) {
        case "Motion":
            console.log(`Motion: ${packetData.description} - Axis ${packetData.axis} = ${packetData.value}`);
            break;
        case "Safety":
            console.log(`Safety: ${packetData.description} - State: ${packetData.state}`);
            break;
        case "OnVIF":
            console.log(`OnVIF: ${packetData.description} - Zoom: ${packetData.zoom}, Measurement: ${packetData.measurement}`);
            break;
    }
});

// Start connection
async function startConnection() {
    try {
        await connection.start();
        console.log("Connected to SignalR hub");
        
        // Register for motion packets
        await registerForMotionPackets();
        
    } catch (err) {
        console.error("Connection failed:", err);
    }
}

// Register for motion packets
async function registerForMotionPackets() {
    const streamRequest = {
        dataPipe: "Motion",
        description: "MOT_GetMotorCurrent",
        isCmd: false,
        axis: 1
    };
    
    try {
        await connection.invoke("RegisterToMethod", streamRequest);
        console.log("Registered for motion packets");
    } catch (err) {
        console.error("Registration failed:", err);
    }
}

// Unregister from motion packets
async function unregisterFromMotionPackets() {
    const streamRequest = {
        dataPipe: "Motion", 
        description: "MOT_GetMotorCurrent",
        isCmd: false,
        axis: 1
    };
    
    try {
        const subscriptionKey = `${streamRequest.dataPipe}|${streamRequest.description}|${streamRequest.isCmd ?? false}|${streamRequest.axis ?? ""}`.toLowerCase();
        await connection.invoke("UnregisterFromMethod", subscriptionKey);
        console.log("Unregistered from motion packets");
    } catch (err) {
        console.error("Unregistration failed:", err);
    }
}

// Start the connection
startConnection();
```

### REST API Usage Examples

#### Start Capture and Register for Streams

```bash
#!/bin/bash

# 1. Get available devices
DEVICES=$(curl -s "http://localhost:10901/api/v1/range/realtime/devices" | jq -r '.data[]')
echo "Available devices: $DEVICES"

# 2. Start capture on first device
DEVICE=$(echo $DEVICES | head -n1)
curl -X POST "http://localhost:10901/api/v1/range/realtime/start/$DEVICE"

# 3. Wait a moment for services to start
sleep 2

# 4. Now connect to SignalR and register for streams
# (Use the JavaScript example above for SignalR connection)
```

#### Get Range Data and Statistics

```bash
#!/bin/bash

# Get all ranges with pagination
curl -s "http://localhost:10901/api/v1/range/ranges?page=1&pageSize=10" | jq '.'

# Get specific range by ID
RANGE_ID="123e4567-e89b-12d3-a456-426614174000"
curl -s "http://localhost:10901/api/v1/range/ranges/$RANGE_ID" | jq '.'

# Reset statistics
curl -X POST "http://localhost:10901/api/v1/range/reset"
```

### Stream Request Examples

#### Motion Packets
```json
{
  "dataPipe": "Motion",
  "description": "MOT_GetMotorCurrent",
  "isCmd": false,
  "axis": 1
}
```

#### Safety Packets
```json
{
  "dataPipe": "Safety", 
  "description": "DO3_FIRE1",
  "isCmd": true,
  "axis": 0
}
```

#### OnVIF Packets
```json
{
  "dataPipe": "OnVIF",
  "description": "LRF_REQ",
  "isCmd": false,
  "axis": 0
}
```

### Error Handling Examples

#### API Error Response
```json
{
  "success": false,
  "data": null,
  "errorMessage": "Range not found",
  "statusCode": 404,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### SignalR Error ACK
```json
{
  "operationType": "RegisterToMethod",
  "success": false,
  "message": "Invalid stream request parameters"
}
```

---

## Notes

- All timestamps are in UTC format (ISO-8601)
- SignalR connection automatically reconnects with exponential backoff
- Stream subscription keys are auto-generated based on DataPipe, Description, IsCmd, and Axis
- Development endpoints are only available in development environment
- All API responses follow the `ResponseResult<T>` pattern for consistent error handling