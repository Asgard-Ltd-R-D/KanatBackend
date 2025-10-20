namespace PacketProcessing.Utils.Constants;

public static class Constants {
    public static readonly int DEFAULT_MIN_WORKERS = 4;
    public static readonly int DEFAULT_MAX_WORKERS = 16;
    public static readonly int DEFAULT_BATCH_SIZE = 500;
    public static readonly int DEFAULT_BATCH_TIMEOUT_MS = 100;
    public static readonly int DEFAULT_PACKET_SAMPLE_MS = 30;

    public static readonly string REALTIME_METHOD_NAME = "OnReceive";
    public static readonly string PLAYBACK_METHOD_NAME = "OnPlayback";
}