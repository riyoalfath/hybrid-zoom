import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

public class Server {
    private static final int TCP_PORT = 8000;

    // Map: ClientKey -> ClientHandler (Untuk kirim pesan)
    private static final Map<String, ClientHandler> activeHandlers = new ConcurrentHashMap<>();
    // Map: ClientKey -> ClientInfo (Untuk simpan data room)
    private static final Map<String, ClientInfo> clients = new ConcurrentHashMap<>();
    
    public static void main(String[] args) {
        try {
            System.out.println("=== MULTI-ROOM ZOOM SERVER STARTED ===");
            try (ServerSocket serverSocket = new ServerSocket(TCP_PORT)) {      // Buka TCP Server
                System.out.println("[SERVER] Listening on port " + TCP_PORT);   // Log

                while (true) {
                    Socket socket = serverSocket.accept();                      // Terima koneksi client
                    new Thread(new ClientHandler(socket)).start();              // Handle di thread baru
                }
            }
        } catch (Exception e) { e.printStackTrace(); }                          // Log error
    }

    // Class untuk handle koneksi tiap client
    static class ClientHandler implements Runnable {                            // Implementasi Runnable untuk threading
        private Socket socket;
        private PrintWriter out;
        private BufferedReader in;
        private String clientKey;
        private String roomToken;

        // Constructor
        public ClientHandler(Socket s) { this.socket = s; }

        // Method untuk kirim pesan ke client
        public synchronized void sendMessage(String msg) {
            try {
                if (out != null) {               // Pastikan output stream siap
                    out.println(msg);            // Kirim pesan
                    out.flush();                 // Pastikan pesan terkirim
                }
            } catch (Exception e) {}            // Abaikan error kirim
        }

        @Override
        // Method utama untuk handle komunikasi dengan client
        public void run() {
            try {
                in = new BufferedReader(new InputStreamReader(socket.getInputStream()));    // Input stream dari client
                out = new PrintWriter(socket.getOutputStream(), true);            // Output stream ke client

                // Kirim IP Detected ke Client
                String detectedIP = socket.getInetAddress().getHostAddress();               // Dapatkan IP Detected
                out.println("YOU|" + detectedIP);                                           // Kirim ke client

                // Terima pesan dari Client
                String msg;
                while ((msg = in.readLine()) != null) {

                    // --- LOGIC JOIN ROOM ---
                    if (msg.startsWith("JOIN|")) {
                        String[] parts = msg.split("\\|");            // Format: JOIN|name|roomToken|localIP|udpPort
                        String name = parts[1];                             // Nama pengguna
                        this.roomToken = parts[2];                          // Token room
                        String localIP = parts[3];                          // IP Lokal client
                        int udpPort = Integer.parseInt(parts[4]);           // Port UDP client

                        // Simpan info client
                        clientKey = detectedIP + ":" + udpPort;             // Buat client key unik
                        ClientInfo newClient = new ClientInfo(clientKey, detectedIP, localIP, udpPort, roomToken, name); // Buat objek ClientInfo

                        // Simpan ke map
                        clients.put(clientKey, newClient);                 // Simpan info client
                        activeHandlers.put(clientKey, this);               // Simpan handler aktif

                        // Log
                        System.out.println(">> [" + roomToken + "] " + name + " Joined");

                        // Kirim info peer ke semua client di room yang sama
                        for (Map.Entry<String, ClientInfo> entry : clients.entrySet()) {
                            ClientInfo c = entry.getValue();                                // Dapatkan info client
                            ClientHandler h = activeHandlers.get(c.key);                    // Dapatkan handler client

                            // Syarat kirim peer: bukan diri sendiri DAN token room SAMA
                            if (c.roomToken.equals(this.roomToken) && !c.key.equals(clientKey)) {
                                h.sendMessage("PEER|" + detectedIP + "|" + localIP + "|" + udpPort + "|" + name);
                                this.sendMessage("PEER|" + c.detectedIp + "|" + c.localIp + "|" + c.udpPort + "|" + c.name);
                            }
                        }
                    }

                    // --- LOGIC RELAY MEDIA & CHAT ---
                    else if (msg.startsWith("VIDEO|") || msg.startsWith("AUDIO|") || msg.startsWith("CHAT|")) { // Format: TYPE|data...

                        // Relay pesan ke semua client di room yang sama
                        for (Map.Entry<String, ClientInfo> entry : clients.entrySet()) {
                            ClientInfo c = entry.getValue();                                // Dapatkan info client
                            ClientHandler h = activeHandlers.get(c.key);                    // Dapatkan handler client

                            // Syarat Relay: Bukan diri sendiri DAN Room Token SAMA
                            if (h != this && c.roomToken.equals(this.roomToken)) { 
                                h.sendMessage(msg);                                          // Kirim pesan    
                            }
                        }
                    }
                }
            } catch (Exception e) {
                // e.printStackTrace();    // Untuk debugging, bisa di-uncomment
            } finally {
                if (clientKey != null) {                           // Hapus client saat disconnect
                    clients.remove(clientKey);                     // Hapus dari list clients   
                    activeHandlers.remove(clientKey);              // Kirim info client keluar ke semua di room yang sama
                    System.out.println(">> Client Left");
                }
            }
        }
    }

    // Class untuk menyimpan info client
    static class ClientInfo {
        String key;
        String detectedIp;
        String localIp;
        int udpPort;
        String roomToken;
        String name;

        public ClientInfo(String k, String det, String loc, int port, String room, String n) {
            this.key = k; this.detectedIp = det; this.localIp = loc; this.udpPort = port;
            this.roomToken = room; this.name = n;
        }
    }
}