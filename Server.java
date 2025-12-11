import java.net.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

public class Server {
    private static final int TCP_PORT = 8000;

    // KITA UBAH JADI 'PUBLIC' AGAR BISA DIAKSES OLEH ClientHandler.java
    public static final Map<String, ClientHandler> activeHandlers = new ConcurrentHashMap<>();
    public static final Map<String, ClientInfo> clients = new ConcurrentHashMap<>();

    public static void main(String[] args) {
        try {
            System.out.println("=== HYBRID ZOOM SERVER STARTED ===");
            try (ServerSocket serverSocket = new ServerSocket(TCP_PORT)) {
                System.out.println("[SERVER] Listening on port " + TCP_PORT);

                while (true) {
                    Socket socket = serverSocket.accept();
                    // Memanggil class ClientHandler yang sekarang sudah di file terpisah
                    new Thread(new ClientHandler(socket)).start();
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}