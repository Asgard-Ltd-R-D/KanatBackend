using System;
using System.Collections.Concurrent;

namespace PacketProcessing.Utils.Observers
{
    /// <summary>
    /// Generic unsubscriber helper for IObservable<T> implementations.
    /// Works with thread-safe collections of observers.
    /// </summary>
    /// <typeparam name="T">Event type observed</typeparam>
    public sealed class Unsubscriber<T> : IDisposable
    {
        private readonly ICollection<IObserver<T>> _observers;
        private readonly IObserver<T> _observer;

        public Unsubscriber(ICollection<IObserver<T>> observers, IObserver<T> observer)
        {
            _observers = observers ?? throw new ArgumentNullException(nameof(observers));
            _observer = observer ?? throw new ArgumentNullException(nameof(observer));
        }

        public void Dispose()
        {
            if (_observers.Contains(_observer))
                _observers.Remove(_observer);
        }
    }

    /// <summary>
    /// Variant for thread-safe collections (ConcurrentDictionary).
    /// </summary>
    /// <typeparam name="T">Event type observed</typeparam>
    public sealed class ConcurrentUnsubscriber<T> : IDisposable
    {
        private readonly ConcurrentDictionary<IObserver<T>, byte> _observers;
        private readonly IObserver<T> _observer;

        public ConcurrentUnsubscriber(ConcurrentDictionary<IObserver<T>, byte> observers, IObserver<T> observer)
        {
            _observers = observers ?? throw new ArgumentNullException(nameof(observers));
            _observer = observer ?? throw new ArgumentNullException(nameof(observer));
        }

        public void Dispose()
        {
            _observers.TryRemove(_observer, out _);
        }
    }
}
