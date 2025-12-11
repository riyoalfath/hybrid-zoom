import java.io.*;
import java.net.*;
import java.util.*;

public class ClientHandler implements Runnable {
    private Socket socket;
    private PrintWriter out;
    private BufferedReader in;
    private String clientKey;
    private String roomToken;
    private String detectedIP;

    public ClientHandler(Socket s) {
        this.socket = s;
    }

    public synchronized void sendMessage(String msg) {
        try {
            if (out != null) {
                out.println(msg);
                out.flush();
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    @Override
    public void run() {
        try {
            in = new BufferedReader(new InputStreamReader(socket.getInputStream()));
            out = new PrintWriter(socket.getOutputStream(), true);

            // Ambil IP Public (Detected IP)
            this.detectedIP = socket.getInetAddress().getHostAddress();

            // Kirim IP Public ke Client (Handshake)
            out.println("YOU|" + detectedIP);

            String msg;
            while ((msg = in.readLine()) != null) {

                // --- LOGIC JOIN ROOM ---
                if (msg.startsWith("JOIN|")) {
                    String[] parts = msg.split("\\|");
                    String name = parts[1];
                    this.roomToken = parts[2];
                    String localIP = parts[3];
                    int udpPort = Integer.parseInt(parts[4]);

                    clientKey = detectedIP + ":" + udpPort;
                    ClientInfo newClient = new ClientInfo(clientKey, detectedIP, localIP, udpPort, roomToken, name);

                    // Akses Map static di class Server
                    Server.clients.put(clientKey, newClient);
                    Server.activeHandlers.put(clientKey, this);

                    System.out.println(">> [" + roomToken + "] " + name + " Joined | Public IP: " + detectedIP + " | Local IP: " + localIP);

                    // Looping Logic
                    for (Map.Entry<String, ClientInfo> entry : Server.clients.entrySet()) {
                        ClientInfo c = entry.getValue();
                        ClientHandler h = Server.activeHandlers.get(c.key);

                        if (c.roomToken.equals(this.roomToken) && !c.key.equals(clientKey)) {
                            h.sendMessage("PEER|" + detectedIP + "|" + localIP + "|" + udpPort + "|" + name);
                            this.sendMessage("PEER|" + c.detectedIp + "|" + c.localIp + "|" + c.udpPort + "|" + c.name);
                        }
                    }
                }

                // --- LOGIC EXIT ---
                else if (msg.startsWith("EXIT|")) {
                    System.out.println(">> [" + roomToken + "] Client request EXIT: " + clientKey + " | Public IP: " + detectedIP);

                    for (Map.Entry<String, ClientInfo> entry : Server.clients.entrySet()) {
                        ClientInfo c = entry.getValue();
                        ClientHandler h = Server.activeHandlers.get(c.key);

                        if (c.roomToken.equals(this.roomToken) && !c.key.equals(clientKey)) {
                            h.sendMessage("REMOVE_PEER|" + detectedIP);
                        }
                    }
                    break;
                }

                // --- RELAY VIDEO / AUDIO / CHAT ---
                else if (msg.startsWith("VIDEO|") || msg.startsWith("AUDIO|") || msg.startsWith("CHAT|")) {
                    for (Map.Entry<String, ClientInfo> entry : Server.clients.entrySet()) {
                        ClientInfo c = entry.getValue();
                        ClientHandler h = Server.activeHandlers.get(c.key);

                        if (h != this && c.roomToken.equals(this.roomToken)) {
                            h.sendMessage(msg);
                        }
                    }
                }
            }
        } catch (Exception e) {
            // e.printStackTrace(); 
        } finally {
            if (clientKey != null) {
                Server.clients.remove(clientKey);
                Server.activeHandlers.remove(clientKey);
                System.out.println(">> Client Disconnected: " + clientKey + " | Public IP: " + detectedIP);
            }
        }
    }
}