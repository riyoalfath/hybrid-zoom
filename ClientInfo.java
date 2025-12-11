public class ClientInfo {
    // Kita buat public agar bisa diakses langsung oleh Server dan ClientHandler
    public String key;
    public String detectedIp;
    public String localIp;
    public int udpPort;
    public String roomToken;
    public String name;

    public ClientInfo(String k, String det, String loc, int port, String room, String n) {
        this.key = k;
        this.detectedIp = det;
        this.localIp = loc;
        this.udpPort = port;
        this.roomToken = room;
        this.name = n;
    }
}