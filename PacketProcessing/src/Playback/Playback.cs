// using System.Buffers;
// using Microsoft.Extensions.Logging;
// using PacketProcessing.DTOs.Data;
// using PacketProcessing.Entities;
// using PacketProcessing.Utils.Enums;
// using PacketProcessing.Utils.Filters;

// namespace PacketProcessing.Playback;

// public sealed class Playback<T> : IDisposable where T : BasePacketEntity
// {
//     public delegate Task TransmitDelegate(PlainDataDto dto, string methodName);
//     public delegate Task<IEnumerable<T>> FetchPageDelegate( DateTime startUtc, DateTime endUtc, int interval, OrderBy orderBy, int page, int pageSize) where T : BasePacketEntity;

//     private readonly ILogger<Playback<T>> _logger;
//     private readonly TransmitDelegate _transmit;
//     private readonly FetchPageDelegate _fetch;
//     private Task? _playbackTask;
//     private readonly IReadOnlyDictionary<string, object>? _filters;
//     private readonly CancellationTokenSource _cancellationTokenSource;

//     private int _isPlaying; // 0: not playing, 1: playing
//     private bool _disposed = false;

//     public Playback(ILogger<Playback<T>> logger, TransmitDelegate transmit, FetchPageDelegate fetch, IReadOnlyDictionary<string, object>? filters = null)
//     {
//         _logger = logger ?? throw new ArgumentNullException(nameof(logger));
//         _transmit = transmit ?? throw new ArgumentNullException(nameof(transmit));
//         _fetch = fetch ?? throw new ArgumentNullException(nameof(fetch));
//         _filters = filters ?? new Dictionary<string, object>();
//         _cancellationTokenSource = new CancellationTokenSource();
//     }

//     /// <summary>
//     /// Start the playback
//     /// </summary>
//     /// <returns>A task representing the asynchronous operation</returns>
//     public Task StartPlaybackAsync() {
//         if (_disposed) throw new ObjectDisposedException(nameof(Playback<T>));
//         if (Interlocked.Exchange(ref _isPlaying, 1) == 1) return Task.CompletedTask;

//         _playbackTask = Task.Run(async () => {
//             var pool = ArrayPool<PlainDataDto>.Shared;
//             PlainDataDto[]? currBuf = null, nextBuf = null;
        
//             try 
//             {
//                 var page = 1;
//                 var pageSize = 1000;

//                 // state: do we already have currBuf primed from last prefetch?
//                 var primed = false;
//                 var currCount = 0;

//                 while (Volatile.Read(ref _isPlaying) == 1 && !_cancellationTokenSource.Token.IsCancellationRequested) {
//                     // get filter values
//                     var start         = GetFilter<DateTime>("start", DateTime.UtcNow.AddMinutes(-5));
//                     var end           = GetFilter<DateTime>("end",   DateTime.UtcNow);
//                     var intervalMs    = GetFilter<int>("interval", 300); // ms
//                     var methodName    = GetFilter<string>("methodName", "");

//                     // rent buffers
//                     currBuf = pool.Rent(pageSize);
//                     nextBuf = pool.Rent(pageSize);

//                     // If not primed by previous prefetch, fetch this page now
//                     if (!primed)
//                     {
//                         currCount = await FetchAndFilterIntoBuffer(start, end, intervalMs, page, pageSize, currBuf)
//                             .ConfigureAwait(false);

//                         // STOP only when _fetch returned nothing (null or zero)
//                         if (Volatile.Read(ref _isPlaying) != 1 || _cancellationTokenSource.Token.IsCancellationRequested)
//                         {
//                             Interlocked.Exchange(ref _isPlaying, 0);
//                             break;
//                         }

//                         if (currCount == 0)
//                         {
//                             page++;
//                             await Task.Delay(10, _cancellationTokenSource.Token).ConfigureAwait(false);
//                             continue;
//                         }
//                     }
//                     else
//                     {
//                         // consume the primed page once; next iteration will fetch/prime again
//                         primed = false;
//                     }

//                     // prefetch state
//                     var lowWater = Math.Max(1, pageSize / 2); // half-page threshold
//                     Task<int>? prefetch = null;
//                     var nextPage = page + 1;

//                     // single transmit loop
//                     for (int i = 0; i < currCount && Volatile.Read(ref _isPlaying) == 1 && !_cancellationTokenSource.Token.IsCancellationRequested; i++)
//                     {
//                         var remaining = currCount - i - 1;
//                         if (prefetch is null && remaining <= lowWater)
//                         {
//                             // kick prefetch of the next page into nextBuf
//                             prefetch = FetchAndFilterIntoBuffer(start, end, intervalMs, nextPage, pageSize, nextBuf);
//                         }

//                         await _transmit(currBuf[i], methodName).ConfigureAwait(false);
//                     }

//                     // check if we should continue
//                     if (Volatile.Read(ref _isPlaying) != 1 || _cancellationTokenSource.Token.IsCancellationRequested) break;

//                     // finalize prefetch; only STOP if _fetch returned nothing
//                     var nextCount = prefetch is null ? 0 : await prefetch.ConfigureAwait(false);
//                     if (nextCount <= 0 || Volatile.Read(ref _isPlaying) != 1 || _cancellationTokenSource.Token.IsCancellationRequested)
//                     {
//                         Interlocked.Exchange(ref _isPlaying, 0);
//                         break;
//                     }
                    
//                     // swap buffers; next loop will transmit the primed page
//                     (currBuf, nextBuf) = (nextBuf, currBuf);
//                     currCount = nextCount;
//                     page = nextPage;
//                     primed = true;
//                 }
//             }
//             catch (OperationCanceledException)
//             {
//                 _logger.LogInformation("Playback operation was cancelled");
//             }
//             catch (Exception ex)
//             {
//                 _logger.LogError(ex, "Error in playback task");
//             }
//             finally
//             {
//                 Interlocked.Exchange(ref _isPlaying, 0);
//                 if (currBuf is not null) pool.Return(currBuf, clearArray: false);
//                 if (nextBuf is not null) pool.Return(nextBuf, clearArray: false);            
//             }
//         }, _cancellationTokenSource.Token);

//         return Task.CompletedTask;
//     }

//     public async Task StopPlaybackAsync() {
//         Interlocked.Exchange(ref _isPlaying, 0);
        
//         if (_playbackTask != null)
//         {
//             try
//             {
//                 await _playbackTask.ConfigureAwait(false);
//             }
//             catch (OperationCanceledException)
//             {
//                 // Expected when cancelling
//             }
//         }
        
//         // Dispose after stopping
//         Dispose();
//     }

//     public bool IsPlaying => Volatile.Read(ref _isPlaying) == 1 && !_disposed;

//     private async Task<int> FetchAndFilterIntoBuffer(
//         DateTime start, 
//         DateTime end, 
//         int intervalMs, 
//         int page, 
//         int pageSize, 
//         PlainDataDto[] buffer) 
//     {
//         if (_disposed || _cancellationTokenSource.Token.IsCancellationRequested) return 0;

//         // fetch raw items from the repository with a specific interval between items
//         var raw = await _fetch(start, end, intervalMs, OrderBy.Asc, page, pageSize).ConfigureAwait(false);
//         if (raw is null)
//         {
//             // fetch returned null, no data anymore, stop playback
//             Interlocked.Exchange(ref _isPlaying, 0);
//             return 0;
//         }

//         // filter the raw items using the provided filters
//         var filtered = await FilterMapper.MapAsync(raw, _filters).ConfigureAwait(false);
//         if (filtered is null) return 0;
        
//         // enumerate directly into the provided array
//         var i = 0;
//         foreach (var item in filtered)
//         {
//             if (i >= buffer.Length || _cancellationTokenSource.Token.IsCancellationRequested) break;
//             buffer[i++] = item;
//         }

//         return i;
//     }

//     private TVal GetFilter<TVal>(string key, TVal fallback)
//     {
//         if (_filters is null) return fallback;
//         if (_filters.TryGetValue(key, out var obj) && obj is TVal v) return v;
//         try
//         {
//             if (_filters.TryGetValue(key, out obj) && obj is not null)
//                 return (TVal) Convert.ChangeType(obj, typeof(TVal))!;
//         }
//         catch { /* ignore */ }
//         return fallback;
//     }

//     public void Dispose()
//     {
//         if (_disposed) return;

//         try
//         {
//             // Stop playback first
//             Interlocked.Exchange(ref _isPlaying, 0);
            
//             // Cancel any ongoing operations
//             _cancellationTokenSource.Cancel();
            
//             // Wait for playback task to complete (with timeout)
//             if (_playbackTask != null)
//             {
//                 try
//                 {
//                     _playbackTask.Wait(TimeSpan.FromSeconds(5));
//                 }
//                 catch (AggregateException ex) when (ex.InnerException is OperationCanceledException)
//                 {
//                     // Expected when cancelling
//                 }
//             }
//         }
//         catch (Exception ex)
//         {
//             _logger?.LogError(ex, "Error during Playback disposal");
//         }
//         finally
//         {
//             _cancellationTokenSource.Dispose();
//             _disposed = true;
//         }
//     }
// }