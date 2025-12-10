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
            ServerSocket serverSocket = new ServerSocket(TCP_PORT);
            System.out.println("[SERVER] Listening on port " + TCP_PORT);

            while (true) {
                Socket socket = serverSocket.accept();
                new Thread(new ClientHandler(socket)).start();
            }
        } catch (Exception e) { e.printStackTrace(); }
    }

    // Class untuk handle koneksi tiap client
    static class ClientHandler implements Runnable {
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
                if (out != null) {
                    out.println(msg);
                    out.flush();
                }
            } catch (Exception e) { }
        }

        @Override
        // Method utama untuk handle komunikasi dengan client
        public void run() {
            try {
                in = new BufferedReader(new InputStreamReader(socket.getInputStream()));
                out = new PrintWriter(socket.getOutputStream(), true);

                // Kirim IP Detected ke Client
                String detectedIP = socket.getInetAddress().getHostAddress();
                out.println("YOU|" + detectedIP);

                // Terima pesan dari Client
                String msg;
                while ((msg = in.readLine()) != null) {

                    // --- LOGIC JOIN ROOM ---
                    if (msg.startsWith("JOIN|")) {
                        String[] parts = msg.split("\\|");
                        String name = parts[1];
                        this.roomToken = parts[2];
                        String localIP = parts[3];
                        int udpPort = Integer.parseInt(parts[4]);

                        // Simpan info client
                        clientKey = detectedIP + ":" + udpPort;
                        ClientInfo newClient = new ClientInfo(clientKey, detectedIP, localIP, udpPort, roomToken, name);

                        // Simpan ke map
                        clients.put(clientKey, newClient);
                        activeHandlers.put(clientKey, this);

                        // Log
                        System.out.println(">> [" + roomToken + "] " + name + " Joined");

                        // Kirim info peer ke semua client di room yang sama
                        for (Map.Entry<String, ClientInfo> entry : clients.entrySet()) {
                            ClientInfo c = entry.getValue();
                            ClientHandler h = activeHandlers.get(c.key);

                            // Syarat kirim peer: bukan diri sendiri DAN token room SAMA
                            if (c.roomToken.equals(this.roomToken) && !c.key.equals(clientKey)) {
                                h.sendMessage("PEER|" + detectedIP + "|" + localIP + "|" + udpPort + "|" + name);
                                this.sendMessage("PEER|" + c.detectedIp + "|" + c.localIp + "|" + c.udpPort + "|" + c.name);
                            }
                        }
                    }

                    // --- LOGIC RELAY MEDIA & CHAT ---
                    else if (msg.startsWith("VIDEO|") || msg.startsWith("AUDIO|") || msg.startsWith("CHAT|")) {

                        // Relay pesan ke semua client di room yang sama
                        for (Map.Entry<String, ClientInfo> entry : clients.entrySet()) {
                            ClientInfo c = entry.getValue();
                            ClientHandler h = activeHandlers.get(c.key);

                            // Syarat Relay: Bukan diri sendiri DAN Room Token SAMA
                            if (h != this && c.roomToken.equals(this.roomToken)) {
                                h.sendMessage(msg);
                            }
                        }
                    }
                }
            } catch (Exception e) {
            } finally {
                if (clientKey != null) {
                    clients.remove(clientKey);
                    activeHandlers.remove(clientKey);
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