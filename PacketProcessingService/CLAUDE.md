# PacketProcessingService

## Architecture

The whole ingest path is generic over `T : BasePacketEntity`, with exactly three concrete types — `MotionPacketEntity`, `SafetyPacketEntity`, `OnVIFPacketEntity`. Adding a fourth packet type means touching the same set of places for each of them:

```
LibPcap device ──> DeviceService (one LibPcapLiveDevice per observer, BPF filter)
   └─ RawPacketEvent (ArrayPool-rented buffer) ──> raw Channel (bounded, per pipe)
        └─ HandlerService<T> (N workers, batches of 64) — ParseMapper → parser
              ├─> TransmissionService.OnNext(entity)   → SignalR, live
              └─> parsed Channel<T> ──> DbWriterService<T> (N workers) → QuestDB ILP
```

- **DI is hand-wired** in `src/Config/ConfigurationInjection.cs`: channels, handlers, writers, parsers, telemetry. Each `HandlerService<T>`/`DbWriterService<T>` is registered three times — as the concrete type, as `I…Service<T>`, and as `IHostedService` — so the same singleton is both injectable and a running `BackgroundService`. New pipe types must be added in all three registrations plus a `Channel<T>`.
- **Backpressure, not drops**: channels use `BoundedChannelFullMode.Wait`. A full channel blocks the producer (`OnNext` does a sync-over-async `WriteAsync`) and increments a backpressure counter. Buffers come from `ArrayPool<byte>.Shared` and are returned in `HandlerService.ProcessBatchAsync`'s `finally` — any new path that consumes `RawPacketEvent.Data` must return the array.
- **Two databases, different jobs.** PostgreSQL via EF Core (`PostgresDbContext`, `EfRepository<T>`) holds range/event/hit/target metadata. QuestDB holds packets: writes go over ILP (`net-questdb-client`, `WriteColumns(ISender)` on each entity), reads over the PG wire protocol with Dapper (`QuestDbContext`, `InfluxRepository<T>`). Table names come from `[Table(...)]`/`Constants.*_PACKETS_TAG`; per-session tables are `{base}_{rangeId:N}`, created on `StopRealtimeRangeAsync` by copying out of the live tables.
- **Subscription keys** are the SignalR routing identity, built by `BasePacketEntity.GetSubscriptionKey()`: `{DataPipe}|{Description}|{IsCmd}` lowercased, plus `|{Axis}` for motion. `TransmissionService` keeps three `ConcurrentDictionary`s keyed by it (connection, interval, last-sent) and does per-key time sampling; `intervalMs == 0` means "no sampling".
- **Two hubs**: `/hubs/packets` (`CustomHub` — register/unregister/set-interval, `OnReceivePacket`/`Ack` events) and `/hubs/telemetry` (`TelemetryHub`, pushed by the `TelemetryBroadcaster` hosted service, rate-limited by `Telemetry:MaxPushRateHz`).
- **Stats** flow through one singleton `StatsObserver` shared by every handler and writer; `RealtimeService.GetStats()` reads a `TelemetryService` snapshot rather than querying components.
- **Mode**: `RangeService` owns `States.Realtime` vs `States.Playback` and delegates to `RealtimeService` / `PlaybackService`; controllers (`RangeController`, `ModeController`) are thin.

## Configuration

`appsettings.json` holds defaults; `appsettings.{Environment}.json` overrides and env vars win (`EnvironmentConfiguration.LoadConfigurations`, base path = `AppContext.BaseDirectory`, so config is read from the *output* dir — a stale `bin/` copy is a common source of confusion).

- `Application:Url` sets the listen URL directly (`UseUrls`), not `ASPNETCORE_URLS`.
- `Concurrency` → worker count is `Math.Clamp(ProcessorCount, MinWorkers, MaxWorkers)`; `BatchSize`/`BatchTimeoutMs` become QuestDB ILP `auto_flush_rows`/`auto_flush_interval`.
- `DataPipes:{Pipe}:Channel:Members` sizes *both* the raw and parsed channels for that pipe. `DataPipes:{Pipe}:Network` (device/protocol/IPs) is only a fallback — at runtime the BPF filter is built by `BpfFilterBuilder` from the `BpfConfig` in the start-range request.
- `SkipDatabaseInitialization=true` bypasses migrations; integration tests set it along with `UseEnvironment("Test")` in `SharedWebApplicationFactory`.
