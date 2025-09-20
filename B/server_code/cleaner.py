import time
import threading
from protocol.constants import GOODBYE
from protocol.header import pack_header
from .session import sessions, sessions_lock, server_seq_num

def session_cleaner(server_socket, timeout_seconds=30):
    global server_seq_num
    while True:
        time.sleep(5)
        now = time.time()
        expired = []
        with sessions_lock:
            for sid, data in list(sessions.items()):
                if now - data['last_seen_time'] > timeout_seconds:
                    expired.append((sid, data['address']))
                    del sessions[sid]
        for sid, addr in expired:
            print(f"0x{sid:08x} Session timed out. Closing.")
            with sessions_lock:
                seq = server_seq_num
                server_seq_num += 1
            packet = pack_header(GOODBYE, seq, sid)
            server_socket.sendto(packet, addr)

def start_cleaner(server_socket):
    t = threading.Thread(target=session_cleaner, args=(server_socket,), daemon=True)
    t.start()
    print("Started session cleaner thread.")
