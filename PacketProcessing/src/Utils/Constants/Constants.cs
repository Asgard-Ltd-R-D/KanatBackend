namespace PacketProcessing.Utils.Constants;

public static class Constants {
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

    // Data pipes names
    public const string MOTION_PACKETS_TAG = "motion_packets";
    public const string ONVIF_PACKETS_TAG = "onvif_packets";
    public const string SAFETY_PACKETS_TAG = "safety_packets";
}