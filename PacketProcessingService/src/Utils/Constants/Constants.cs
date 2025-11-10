namespace PacketProcessing.Utils.Constants;

public static class Constants {
    public const string SIGNALR_ON_RECEIVE_PACKET = "OnReceivePacket";
    public const string SIGNALR_ACK = "Ack";

    // ONVIF constants
    public const ushort ONVIF_REPORT_TCP_PORT=8080;
    public const string ONVIF_XML_DAY="day";
    public const string ONVIF_XML_NIGHT="night_combined";
    public const string ONVIF_XML_LRF="laser_range_finder";

    // Motion packet constants
    public const ushort MOTION_REPORT_PORT=4949;

    // OnVIF packet descriptions
    public const string ONVIF_FOV_REQ="FOV_REQ";
    public const string ONVIF_FOV_STS="FOV_STS";
    public const string ONVIF_LRF_REQ="LRF_REQ";
    public const string ONVIF_LRF_STS="LRF_STS";

    // Safety packet constants
    public const string PBE_IP="132.8.7.101";
    public const string SBE_IP="132.8.7.102";

    // Data pipes names
    public const string MOTION_PACKETS_TAG = "motion_packets";
    public const string ONVIF_PACKETS_TAG = "onvif_packets";
    public const string SAFETY_PACKETS_TAG = "safety_packets";

    // Entity names
    public const string MOTION_ENTITY_NAME = "Motion";
    public const string ONVIF_ENTITY_NAME = "OnVIF";
    public const string SAFETY_ENTITY_NAME = "Safety";

    // Raw channel names
    public const string MOTION_RAW_CHANNEL_NAME = "MotionRaw";
    public const string ONVIF_RAW_CHANNEL_NAME = "OnVIFRaw";
    public const string SAFETY_RAW_CHANNEL_NAME = "SafetyRaw";
}