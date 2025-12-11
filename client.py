import socket
import threading
import cv2
import numpy as np
import math
import sys
import time
import base64
import pyaudio
import platform
import os
import random
import string
import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext
from PIL import Image, ImageTk, ImageDraw 

# =================================================================
# KONFIGURASI GLOBAL
# =================================================================
SERVER_LAN_IP = "192.168.1.15"   # Ganti dengan IP Server di LAN Anda
SERVER_LAN_PORT = 8000           # Port TCP Server di LAN
PINGGY_HOST = "cavcr-140-213-232-121.a.free.pinggy.link" # Ganti dengan Host Pinggy Anda
PINGGY_PORT = 33681                                      # Port Pinggy

GRID_COLS = 3                   # Jumlah kolom grid video
THUMB_W, THUMB_H = 240, 180     # Ukuran thumbnail video

FIXED_UDP_PORT = 6001           # Port UDP untuk Video
FIXED_AUDIO_PORT = 6002         # Port UDP untuk Audio

# --- STATE VARIABLES ---
is_mic_on = True                # Status Mikrofon, True=On, False=Off
is_cam_on = True                # Status Kamera, True=On, False=Off
is_in_meeting = False           # Status Apakah Sedang di Meeting, False=Tidak

MY_NAME = ""                    # Nama Pengguna
MY_ROOM_TOKEN = ""              # Token Room Meeting

# Audio Config
FORMAT = pyaudio.paInt16    # Format Audio
CHANNELS = 1                # Mono
RATE = 8000                 # Sample Rate
CHUNK = 1024                # Ukuran Chunk

current_os = platform.system() # Deteksi OS: "Windows", "Linux", "Darwin" (Mac)
WIN_OUTPUT_INDEX = None        # Ganti dengan index output audio di Windows Anda, None jika tidak tahu/default
WIN_INPUT_INDEX = None         # Ganti dengan index input audio di Windows Anda, None jika tidak tahu/default

if current_os == "Linux":
    OUTPUT_INDEX = 13      
    INPUT_INDEX = None  
else:
    OUTPUT_INDEX = WIN_OUTPUT_INDEX 
    INPUT_INDEX = WIN_INPUT_INDEX

# =================================================================
# SOCKET INIT
# =================================================================
try:
    sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)          # UDP Socket
    sock_udp.bind(('0.0.0.0', FIXED_UDP_PORT))                           # Bind ke semua interface
    
    sock_audio_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)    # UDP Socket Audio
    sock_audio_udp.bind(('0.0.0.0', FIXED_AUDIO_PORT))                   # Bind ke semua interface
except: pass

sock_tcp = None         # TCP Socket (akan diinisialisasi saat connect)
peers = []              # List Teman (Peers) dalam meeting
active_feeds = {}       # Dictionary frame video aktif {ip_local: frame}
my_local_ip = ""        # <--- Variable untuk simpan IP Lokal kita
my_public_ip = ""       # <--- Variable untuk simpan IP Public kita

chat_display = None     # Text Area untuk chat
root_window = None      # Root Window Tkinter
video_label = None      # Label untuk tampilan video
p = None                # PyAudio Instance
input_stream = None     # Input Audio Stream
output_stream = None    # Output Audio Stream
cap = None              # Video Capture Object

img_mic_on = None       # Gambar ikon mic on
img_mic_off = None      # Gambar ikon mic off
img_cam_on = None       # Gambar ikon cam on
img_cam_off = None      # Gambar ikon cam off

# =================================================================
# FUNGSI UTILITAS
# =================================================================
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)    # Dummy socket
        s.connect(('8.8.8.8', 80))                              # Connect ke Google DNS
        ip = s.getsockname()[0]; s.close()                      # Ambil IP lokal
        return ip                                               
    except: return "127.0.0.1"                                  # Fallback ke localhost

def generate_token():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6)) # Generate 6 karakter untuk token

# =================================================================
# NETWORK LOGIC
# =================================================================
def connect_to_server():
    global sock_tcp     # Gunakan socket TCP global
    
    # --- PERCOBAAN 1: LAN (Lokal) ---
    print(f"[CONNECT] Mencoba LAN: {SERVER_LAN_IP}:{SERVER_LAN_PORT}")
    try:
        # Buat socket baru setiap kali mau connect
        sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)    # TCP Socket
        sock_tcp.settimeout(2)                                          # Timeout 2 detik
        sock_tcp.connect((SERVER_LAN_IP, SERVER_LAN_PORT))              # Coba connect ke Server LAN  
        print("[SUCCESS] Terhubung via LAN")
        return True
    except:
        print("[FAIL] LAN gagal. Mencoba Pinggy...")
    
    # --- PERCOBAAN 2: INTERNET (Pinggy) ---
    print(f"[CONNECT] Mencoba Pinggy: {PINGGY_HOST}:{PINGGY_PORT}")
    try:
        # PENTING: Buat ulang socket baru karena yang lama mungkin error
        sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)    # Reset socket
        sock_tcp.settimeout(10)                                         # Timeout lebih lama untuk internet
        sock_tcp.connect((PINGGY_HOST, PINGGY_PORT))                    # Coba connect ke Server Pinggy
        print("[SUCCESS] Terhubung via Internet (Pinggy)")
        return True
    except Exception as e:
        print(f"[FAIL] Pinggy gagal: {e}")                              # Print error detail di console
        messagebox.showerror("Error", f"Gagal connect ke Server!\n\nLAN: {SERVER_LAN_IP}\nPinggy: {PINGGY_HOST}:{PINGGY_PORT}")
        return False

def handle_tcp():
    global my_local_ip, my_public_ip
    
    # Ambil IP Local Laptop saat ini
    my_local_ip = get_local_ip()
    
    # Coba connect ke Server (LAN dulu, kalau gagal baru Pinggy)
    if not connect_to_server(): return

    sock_tcp.settimeout(None)   # Nonaktifkan timeout setelah connect berhasil
    buffer = b""                # Buffer untuk data TCP masuk
    
    try:
        while is_in_meeting:
            try:
                # Terima data TCP (dipecah per 64KB)
                chunk = sock_tcp.recv(65536)
                if not chunk: break
                
                buffer += chunk
                
                # Proses data jika ada karakter baris baru (\n)
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    msg = line.decode(errors='ignore').strip()

                    # --- 1. SERVER MEMBERI TAHU IDENTITAS KITA ---
                    if msg.startswith("YOU|"):
                        # Format: YOU|IP_PUBLIC_KITA
                        _, detected_ip = msg.split("|")
                        my_public_ip = detected_ip 
                        
                        # Kirim data diri lengkap ke Server (Registrasi)
                        reg_msg = f"JOIN|{MY_NAME}|{MY_ROOM_TOKEN}|{my_local_ip}|{FIXED_UDP_PORT}\n"
                        sock_tcp.send(reg_msg.encode())

                    # --- 2. ADA TEMAN BARU BERGABUNG (PEER) ---
                    elif msg.startswith("PEER|"):
                        # Format: PEER|IP_PUBLIC_TEMAN|IP_LOCAL_TEMAN|PORT|NAMA
                        parts = msg.split("|")
                        if len(parts) >= 5:
                            p_public = parts[1]      # IP Public Teman (Dilihat Server)
                            p_local = parts[2]       # IP Local Teman (Dikirim Teman)
                            p_port = int(parts[3])   # Port UDP Teman
                            p_name = parts[4]        # Nama Teman
                            
                            # Jangan masukkan diri sendiri ke list teman
                            if p_local == my_local_ip: continue 
                            
                            # Cek apakah teman sudah ada di list (biar ga dobel)
                            exists = False
                            for p in peers:
                                # Cek kombinasi: IP Public HARUS SAMA & IP Local HARUS SAMA
                                # Baru bisa dibilang device yang sama
                                if p['public_ip'] == p_public and p['local_ip'] == p_local:
                                    exists = True
                                    break # Ketemu duplikat, stop looping
                            
                            if not exists:
                                # === [LOGIKA DETEKSI HYBRID FINAL & AMAN] ===
                                
                                # A. CEK SUBNET LOKAL
                                # Apakah kepala IP Laptop kita sama? (misal sama-sama 192.168.1.x)
                                my_prefix = ".".join(my_local_ip.split('.')[:3])   # Ambil 3 oktet pertama
                                peer_prefix = ".".join(p_local.split('.')[:3])     # Ambil 3 oktet pertama Teman
                                is_same_subnet = (my_prefix == peer_prefix)        # Cek kesamaan subnet
                                
                                # B. CEK PUBLIC IP (ROUTER)
                                # Apakah kita keluar dari Router Internet yang sama?
                                is_same_router = (my_public_ip == p_public)
                                
                                # C. CEK APAKAH INI JARINGAN LAN MURNI?
                                # Helper function: Cek apakah IP berawalan Private IP (192.168, 10, 172)
                                def is_private(ip):
                                    return ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172.")
                                
                                # Jika Server melihat IP kita dan IP teman sebagai IP Private,
                                # berarti Server berada di LAN yang sama dengan kita (bukan di Internet).
                                both_in_lan_with_server = is_private(my_public_ip) and is_private(p_public)
                                
                                # === KEPUTUSAN FINAL ===
                                mode = "ONLINE (TCP)" # Default: Anggap Jauh (Internet)
                                
                                # Syarat OFFLINE (UDP P2P):
                                # 1. Kita harus satu Subnet Lokal.
                                # 2. DAN (Kita satu Router Internet  ATAU  Kita satu LAN dengan Server).
                                if is_same_subnet and (is_same_router or both_in_lan_with_server):
                                    mode = "OFFLINE (UDP)"
                                    
                                # ===========================================
                                
                                # Simpan data teman ke list
                                peers.append({
                                    'local_ip': p_local, 
                                    'port': p_port, 
                                    'audio_port': p_port+1, 
                                    'mode': mode, 
                                    'name': p_name, 
                                    'public_ip': p_public
                                })
                                update_chat(f"[SYSTEM] {p_name} bergabung via {mode}")

                    # --- 3. TEMAN KELUAR ---
                    elif msg.startswith("REMOVE_PEER|"):
                        left_ip = msg.split("|")[1]
                        
                        # Hapus Video dari GUI
                        keys_to_remove = []
                        for k in active_feeds.keys():
                            if k == left_ip: keys_to_remove.append(k)
                        
                        # Hapus Data Teman dari List Peers
                        for p in peers:
                            if p['public_ip'] == left_ip:
                                keys_to_remove.append(p['local_ip'])
                                update_chat(f"[SYSTEM] {p['name']} telah keluar.")
                                peers.remove(p)
                                break
                        
                        # Bersihkan frame video teman yang keluar
                        for k in keys_to_remove:
                            if k in active_feeds: del active_feeds[k]

                    # --- 4. TERIMA CHAT ---
                    elif msg.startswith("CHAT|"):
                        try:
                            _, sender_name, chat_msg = msg.split("|", 2)
                            update_chat(f"{sender_name}: {chat_msg}")
                        except: pass

                    # --- 5. TERIMA VIDEO RELAY (JIKA TCP) ---
                    elif msg.startswith("VIDEO|"):
                        try:
                            _, sender_ip, b64 = msg.split("|")
                            if sender_ip == my_local_ip: continue
                            # Dekode Base64 ke Gambar
                            data = base64.b64decode(b64)
                            nparr = np.frombuffer(data, np.uint8)
                            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            if frame is not None: active_feeds[sender_ip] = frame
                        except: pass
                    
                    # --- 6. TERIMA AUDIO RELAY (JIKA TCP) ---
                    elif msg.startswith("AUDIO|"):
                        try:
                            _, sender_ip, b64 = msg.split("|")
                            if sender_ip == my_local_ip: continue
                            # Dekode Base64 ke Suara dan Play
                            data = base64.b64decode(b64)
                            output_stream.write(data, exception_on_underflow=False)
                        except: pass

            except socket.error: break
    except: pass
    
def send_chat_message(msg):
    full_msg = f"CHAT|{MY_NAME}|{msg}\n"    # Format pesan chat
    try: sock_tcp.send(full_msg.encode())   # Kirim ke server
    except: pass                            
    update_chat(f"Me: {msg}")               # Tampilkan di chat lokal

def update_chat(text):
    if chat_display:
        chat_display.config(state=tk.NORMAL)
        chat_display.insert(tk.END, text + "\n")
        chat_display.see(tk.END) 
        chat_display.config(state=tk.DISABLED)

def receive_udp_video():                    # Fungsi menerima video via UDP
    while is_in_meeting:
        try:
            data, addr = sock_udp.recvfrom(65507)                # Maks UDP Packet Size
            if addr[0] == my_local_ip: continue                  # Abaikan jika dari diri sendiri
            nparr = np.frombuffer(data, np.uint8)                # Konversi ke array numpy
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)        # Dekode gambar dari array
            if frame is not None: active_feeds[addr[0]] = frame  # Simpan frame berdasarkan IP pengirim
        except: pass

def receive_udp_audio():                    # Fungsi menerima audio via UDP
    while is_in_meeting:
        try:
            data, addr = sock_audio_udp.recvfrom(4096)                  # Maks UDP Packet Size untuk audio
            if addr[0] == my_local_ip: continue                         # Abaikan jika dari diri sendiri
            output_stream.write(data, exception_on_underflow=False)     # Putar audio masuk, exception diabaikan
        except: pass

def microphone_loop():                      # Fungsi mengirim audio dari mikrofon
    while is_in_meeting:
        try:
            data = input_stream.read(CHUNK, exception_on_overflow=False) # Baca data audio dari mikrofon
            if not is_mic_on:                                            # Jika mic mati, kirim data kosong
                time.sleep(0.01)                                         # Sedikit delay agar tidak terlalu cepat
                continue
            
            for p in peers:
                if p['mode'].startswith("OFFLINE"):                      # Kirim via UDP
                    try: sock_audio_udp.sendto(data, (p['local_ip'], p['audio_port']))
                    except: pass
                elif p['mode'].startswith("ONLINE"):                     # Kirim via TCP (Base64)
                    try:
                        b64 = base64.b64encode(data).decode('utf-8')
                        msg = f"AUDIO|{my_local_ip}|{b64}\n"
                        sock_tcp.send(msg.encode())
                    except: pass
        except: pass

def cam_loop():                             # Fungsi mengirim video dari kamera
    global cap
    cap = cv2.VideoCapture(0)               # Inisialisasi kamera
    cap.set(3, 320); cap.set(4, 240)
    black = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.putText(black, "CAM OFF", (100, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
    
    while is_in_meeting:                    # Loop selama di meeting
        if is_cam_on:
            ret, frame = cap.read()
            if not ret: continue
        else:
            frame = black.copy()            # Gunakan frame hitam jika kamera mati
            time.sleep(0.05)
        
        cv2.putText(frame, f"{MY_NAME}", (10, 230), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)    # Nama pengguna
        active_feeds[my_local_ip] = frame
        
        _, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 35])    # Kompresi JPEG dengan kualitas 35
        jpg = buf.tobytes()                                                          # Konversi ke bytes
        for p in peers:
            if p['mode'].startswith("OFFLINE"):                                      # Kirim via UDP
                try: sock_udp.sendto(jpg, (p['local_ip'], p['port']))
                except: pass
            elif p['mode'].startswith("ONLINE"):                                     # Kirim via TCP (Base64)    
                try:
                    b64 = base64.b64encode(jpg).decode('utf-8')
                    msg = f"VIDEO|{my_local_ip}|{b64}\n"
                    sock_tcp.send(msg.encode())
                except: pass
        time.sleep(0.04)
    cap.release()                                                                    # Lepas kamera saat keluar dari meeting

def start_meeting_gui():
    global chat_display, root_window, video_label, is_mic_on, is_cam_on
    # Tambahkan global img_input_bg dan img_send agar tidak hilang
    global img_mic_on, img_mic_off, img_cam_on, img_cam_off, img_exit, img_input_bg, img_send

    root_window = tk.Tk()
    root_window.title(f"Zoom Room: {MY_ROOM_TOKEN}")    # Judul window dengan token room
    root_window.geometry("1300x700")                    # Ukuran window    

    base_folder = os.path.dirname(os.path.abspath(__file__))    # Folder dasar script
    img_folder = os.path.join(base_folder, "img")               # Folder gambar

    # --- CONFIG WARNA ---
    BTN_BG_ON_COLOR   = "#1e2939"   # Warna tombol aktif (mirip gambar referensi)
    BTN_BG_RED_COLOR  = "#ffa2a2"   # Warna tombol non-aktif (mirip gambar referensi)
    FRAME_BG_COLOR    = "#333333"   # Warna background frame kontrol bawah
    
    # Warna untuk Input Chat (Mirip gambar referensi)
    INPUT_BG_COLOR    = "#2b2b2b" # Abu-abu gelap untuk kapsul
    INPUT_TEXT_COLOR  = "#dddddd" # Teks putih abu
    RIGHT_PANEL_BG    = "#1e1e1e" # Background panel kanan kita gelapkan biar cocok

    try:
        # --- LOAD ICON SEBELUMNYA (MIC/CAM/EXIT) ---
        img_mic_on  = create_rounded_icon(os.path.join(img_folder, "mic_on.png"), size=(48, 48), icon_size=(24, 24), bg_color=BTN_BG_ON_COLOR)
        img_mic_off = create_rounded_icon(os.path.join(img_folder, "mic_off.png"), size=(48, 48), icon_size=(24, 24), bg_color=BTN_BG_RED_COLOR)
        img_cam_on  = create_rounded_icon(os.path.join(img_folder, "cam_on.png"), size=(48, 48), icon_size=(24, 24), bg_color=BTN_BG_ON_COLOR)
        img_cam_off = create_rounded_icon(os.path.join(img_folder, "cam_off.png"), size=(48, 48), icon_size=(24, 24), bg_color=BTN_BG_RED_COLOR)
        img_exit    = create_rounded_icon(os.path.join(img_folder, "exit.png"), size=(48, 48), icon_size=(24, 24), bg_color=BTN_BG_RED_COLOR)

        # --- BARU: LOAD ICON SEND & INPUT BG ---
        # 1. Background Kapsul Input
        # Lebar disesuaikan dengan lebar panel kanan (dikurangi padding)
        img_input_bg = create_input_bg(width=280, height=40, bg_color=RIGHT_PANEL_BG, border_radius=20, fill_color=INPUT_BG_COLOR)
        
        # 2. Icon Send (Pesawat Kertas)
        raw_send = Image.open(os.path.join(img_folder, "send.png")).convert("RGBA")
        raw_send = raw_send.resize((20, 20), Image.LANCZOS)
        img_send = ImageTk.PhotoImage(raw_send)

    except Exception as e:
        messagebox.showerror("Warning", f"Gagal memuat gambar: {e}")
        return

    # --- LAYOUT GUI ---
    
    left_frame = tk.Frame(root_window, bg="black")
    left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # Ubah background kanan jadi gelap agar match dengan desain input
    right_frame = tk.Frame(root_window, width=300, bg=RIGHT_PANEL_BG)
    right_frame.pack(side=tk.RIGHT, fill=tk.Y)
    right_frame.pack_propagate(False) # Agar lebar tetap fixed 300px

    video_label = tk.Label(left_frame, bg="black")
    video_label.pack(fill=tk.BOTH, expand=True)

    # Header Room Token
    tk.Label(right_frame, text="Chat Room", font=("Arial", 12, "bold"), 
             bg=RIGHT_PANEL_BG, fg="white").pack(fill=tk.X, pady=10)
    
    # Chat Area
    chat_display = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, width=30, height=20, 
                                             bg=RIGHT_PANEL_BG, fg="white", 
                                             bd=0, highlightthickness=0) # Hilangkan border
    chat_display.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
    
    # --- INPUT AREA CUSTOM (PILL SHAPE) ---
    
    # 1. Container Frame di bawah
    input_container = tk.Frame(right_frame, bg=RIGHT_PANEL_BG, height=60)
    input_container.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
    
    # 2. Label sebagai Background Gambar Kapsul
    bg_label = tk.Label(input_container, image=img_input_bg, bg=RIGHT_PANEL_BG, bd=0)
    bg_label.pack()

    entry_msg = tk.Entry(bg_label, 
                         bg=INPUT_BG_COLOR,      
                         fg=INPUT_TEXT_COLOR,    
                         insertbackground="white", 
                         bd=0,                   # Hapus border 3D
                         highlightthickness=0,   # <--- PENTING: Hapus outline hitam/fokus
                         font=("Arial", 11))
    
    # Placeholder Logic (Teks "Send a message")
    def on_entry_click(event):
        if entry_msg.get() == 'Send a message':
            entry_msg.delete(0, "end") 
            entry_msg.config(fg=INPUT_TEXT_COLOR)

    def on_focus_out(event):
        if entry_msg.get() == '':
            entry_msg.insert(0, 'Send a message')
            entry_msg.config(fg='grey')

    entry_msg.insert(0, 'Send a message')
    entry_msg.config(fg='grey')
    entry_msg.bind('<FocusIn>', on_entry_click)
    entry_msg.bind('<FocusOut>', on_focus_out)
    
    # Fungsi Kirim Wrapper
    def send_action(event=None):
        msg = entry_msg.get()
        if msg and msg != "Send a message":
            send_chat_message(msg)
            entry_msg.delete(0, tk.END) 
    
    entry_msg.bind("<Return>", send_action)

    # --- PERUBAHAN POSISI ---
    # y=10 diubah jadi y=8 (agar naik sedikit ke atas)
    # height ditambah sedikit agar teks tidak terpotong bagian bawahnya
    entry_msg.place(x=15, y=8, width=220, height=24) 

    # 4. Tombol Kirim (Icon Pesawat) ditaruh DI ATAS Label Background
    btn_send = tk.Button(bg_label, 
                         image=img_send, 
                         bg=INPUT_BG_COLOR, 
                         activebackground=INPUT_BG_COLOR,
                         bd=0, 
                         highlightthickness=0, # Hapus outline tombol juga
                         cursor="hand2",
                         command=send_action)
    
    # Atur posisi tombol di kanan kapsul
    # y=8 agar sejajar dengan teks input
    btn_send.place(x=245, y=8)

    # --- CONTROL FRAME BAWAH (MIC/CAM/EXIT) ---
    control_frame = tk.Frame(left_frame, bg=FRAME_BG_COLOR, height=80) 
    control_frame.pack(side=tk.BOTTOM, fill=tk.X)
    control_frame.pack_propagate(False) 

    # (Bagian tombol Mic/Cam/Exit tetap sama seperti kode sebelumnya...)
    if img_mic_on:
        btn_mic = tk.Button(control_frame, image=img_mic_on, bg=FRAME_BG_COLOR, activebackground=FRAME_BG_COLOR, borderwidth=0, highlightthickness=0, command=lambda: toggle_mic(btn_mic))
        btn_cam = tk.Button(control_frame, image=img_cam_on, bg=FRAME_BG_COLOR, activebackground=FRAME_BG_COLOR, borderwidth=0, highlightthickness=0, command=lambda: toggle_cam(btn_cam))
    else:
        btn_mic = tk.Button(control_frame, text="MIC ON", bg="lightgreen", width=10, command=lambda: toggle_mic(btn_mic))
        btn_cam = tk.Button(control_frame, text="CAM ON", bg="lightgreen", width=10, command=lambda: toggle_cam(btn_cam))

    btn_mic.pack(side=tk.LEFT, padx=(30, 15), pady=15)
    btn_cam.pack(side=tk.LEFT, padx=(15, 0), pady=15)

    if img_exit:
        btn_leave = tk.Button(control_frame, image=img_exit, bg=FRAME_BG_COLOR, activebackground=FRAME_BG_COLOR, borderwidth=0, highlightthickness=0, command=confirm_leave)
    else:
        btn_leave = tk.Button(control_frame, text="KELUAR", bg="red", fg="white", width=10, font=("Arial", 10, "bold"), command=confirm_leave)
    btn_leave.pack(side=tk.RIGHT, padx=20, pady=15)

    update_video_gui()
    root_window.protocol("WM_DELETE_WINDOW", lambda: sys.exit())
    root_window.mainloop()
    
def create_input_bg(width, height, bg_color, border_radius, fill_color):
    """
    Membuat background rounded rectangle (kapsul) untuk input field.
    """
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Gambar rounded rect penuh
    draw.rounded_rectangle(
        [(0, 0), (width, height)], 
        radius=border_radius, 
        fill=fill_color
    )
    return ImageTk.PhotoImage(image)

def create_rounded_icon(path, size=(50, 50), icon_size=(24, 24), bg_color="#1e2939", radius=15):
    """
    Membuat gambar rounded rectangle dengan ikon di tengahnya.
    """
    # 1. Buat kanvas transparan
    # Ukuran size (50,50) memberikan padding otomatis dibanding icon_size (24,24)
    base = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(base)
    
    # 2. Gambar Rounded Rectangle (Background)
    # xy adalah koordinat bounding box [(0,0), (lebar, tinggi)]
    draw.rounded_rectangle([(0, 0), size], radius=radius, fill=bg_color)
    
    # 3. Load dan Resize Ikon Asli
    try:
        icon = Image.open(path).convert("RGBA")
        icon = icon.resize(icon_size, Image.LANCZOS)
        
        # 4. Hitung posisi tengah agar ada padding
        center_x = (size[0] - icon_size[0]) // 2
        center_y = (size[1] - icon_size[1]) // 2
        
        # 5. Tempel ikon di atas background
        base.paste(icon, (center_x, center_y), icon)
        
        return ImageTk.PhotoImage(base)
    except Exception as e:
        print(f"Error loading icon {path}: {e}")
        return None

def toggle_mic(btn):
    global is_mic_on
    is_mic_on = not is_mic_on
    
    if img_mic_on: # Jika mode Gambar
        if is_mic_on:
            btn.config(image=img_mic_on)
        else:
            btn.config(image=img_mic_off)

def toggle_cam(btn):
    global is_cam_on
    is_cam_on = not is_cam_on
    
    if img_cam_on: # Jika mode Gambar
        if is_cam_on:
            btn.config(image=img_cam_on)
        else:
            btn.config(image=img_cam_off)

def confirm_leave():
    if messagebox.askyesno("Konfirmasi", "Keluar dari meeting?"):
        leave_meeting()

def leave_meeting():
    global is_in_meeting, peers, active_feeds
    
    # 1. Kirim Sinyal EXIT ke Server
    try:
        msg = f"EXIT|{MY_ROOM_TOKEN}|{my_public_ip}\n"
        sock_tcp.send(msg.encode())
    except: pass
    
    is_in_meeting = False
    time.sleep(0.5) 
    
    try:
        sock_tcp.close()
        input_stream.stop_stream(); input_stream.close()
        output_stream.stop_stream(); output_stream.close()
        p.terminate()
        cap.release()
    except: pass
    
    peers = []
    active_feeds = {}
    root_window.destroy()
    show_login_panel()

def update_video_gui():
    frames = list(active_feeds.values())
    count = len(frames)
    
    if count == 0:
        final_img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(final_img, "Waiting...", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
    else:
        try:
            cols = 3
            rows = math.ceil(count / cols)
            h, w = 240, 320 
            big_canvas = np.zeros((rows * h, cols * w, 3), dtype=np.uint8)
            for i, frame in enumerate(frames):
                small = cv2.resize(frame, (w, h))
                r, c = i // cols, i % cols
                big_canvas[r*h:(r+1)*h, c*w:(c+1)*w] = small
            final_img = big_canvas
        except:
            final_img = np.zeros((480, 640, 3), dtype=np.uint8)

    final_img = cv2.cvtColor(final_img, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(final_img)
    imgtk = ImageTk.PhotoImage(image=img)
    video_label.imgtk = imgtk
    video_label.configure(image=imgtk)
    
    if is_in_meeting:
        root_window.after(30, update_video_gui)

def show_login_panel():
    login_root = tk.Tk()
    login_root.title("Login Zoom Hybrid")
    login_root.geometry("600x400")
    
    tk.Label(login_root, text="Nama Anda:").pack(pady=5)
    v_name = tk.Entry(login_root); v_name.pack()
    tk.Label(login_root, text="Room Token:").pack(pady=5)
    v_token = tk.Entry(login_root); v_token.pack()
    
    def on_act(action):
        global MY_NAME, MY_ROOM_TOKEN, is_in_meeting
        MY_NAME = v_name.get()
        token = v_token.get()
        if not MY_NAME: 
            messagebox.showerror("Error", "Isi Nama dulu!")
            return
        
        if action == "CREATE":
            MY_ROOM_TOKEN = generate_token()
            messagebox.showinfo("Info", f"Room Created: {MY_ROOM_TOKEN}")
            v_token.delete(0, tk.END); v_token.insert(0, MY_ROOM_TOKEN)
        else:
            if not token: 
                messagebox.showerror("Error", "Isi Token Room!")
                return
            MY_ROOM_TOKEN = token
            is_in_meeting = True
            login_root.destroy()
            start_main_app()

    tk.Button(login_root, text="Buat Room", command=lambda: on_act("CREATE"), bg="cyan").pack(pady=5)
    tk.Button(login_root, text="Gabung Room", command=lambda: on_act("JOIN"), bg="lime").pack(pady=5)
    login_root.mainloop()

def start_main_app():
    global p, input_stream, output_stream
    p = pyaudio.PyAudio()
    try:
        input_stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK, input_device_index=INPUT_INDEX)
        output_stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK, output_device_index=OUTPUT_INDEX)
    except: pass

    threading.Thread(target=handle_tcp, daemon=True).start()
    threading.Thread(target=receive_udp_video, daemon=True).start()
    threading.Thread(target=receive_udp_audio, daemon=True).start()
    threading.Thread(target=microphone_loop, daemon=True).start()
    threading.Thread(target=cam_loop, daemon=True).start()
    start_meeting_gui()

show_login_panel()