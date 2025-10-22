namespace PacketProcessing.Utils.Constants;

public static class Constants {
    public static readonly int DEFAULT_MIN_WORKERS = 4;
    public static readonly int DEFAULT_MAX_WORKERS = 16;
    public static readonly int DEFAULT_BATCH_SIZE = 500;
    public static readonly int DEFAULT_BATCH_TIMEOUT_MS = 100;
    public static readonly int DEFAULT_PACKET_SAMPLE_MS = 30;

    public const string SIGNALR_ON_RECEIVE_PACKET = "OnReceivePacket";
    public const string SIGNALR_ACK = "Ack";

    // ONVIF constants
    public const string ONVIF_REPORT_IP="132.8.7.121";
    public const string ONVIF_XML_DAY="day";
    public const string ONVIF_XML_NIGHT="night_combined";
    public const string ONVIF_XML_LRF="laser_range_finder";

    // OnVIF packet descriptions
    public const string ONVIF_FOV_REQ="FOV_REQ";
    public const string ONVIF_FOV_STS="FOV_STS";
    public const string ONVIF_LRF_REQ="LRF_REQ";
    public const string ONVIF_LRF_STS="LRF_STS";
}