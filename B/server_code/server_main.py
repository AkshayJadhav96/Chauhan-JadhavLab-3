import socket, sys, threading
from protocol.header import unpack_header, pack_header
from protocol.constants import GOODBYE
from .worker import start_workers
from .cleaner import start_cleaner
from .session import sessions, sessions_lock, server_seq_num

BUFFER_SIZE = 1024

def input_handler(shutdown_event):
    while not shutdown_event.is_set():
        line = sys.stdin.readline()
        try:
            if not line or (sys.stdin.isatty() and line.strip() == 'q'):
                shutdown_event.set()
        except (KeyboardInterrupt, EOFError):
            shutdown_event.set()

def main():
    if len(sys.argv) != 2:
        print("Usage: ./server <portnum>")
        sys.exit(1)
    port = int(sys.argv[1])
    shutdown_event = threading.Event()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
        server_socket.bind(('', port))
        server_socket.settimeout(1.0)
        print(f"Server listening on port {port}...")

        worker_queues = start_workers(server_socket)
        start_cleaner(server_socket)
        threading.Thread(target=input_handler, args=(shutdown_event,), daemon=True).start()

        while not shutdown_event.is_set():
            try:
                data, address = server_socket.recvfrom(BUFFER_SIZE)
                header = unpack_header(data)
                if header:
                    idx = header['session_id'] % len(worker_queues)
                    worker_queues[idx].put((data, address))
            except socket.timeout:
                continue

        print("Shutting down, sending GOODBYE to clients...")
        with sessions_lock:
            for sid, data in sessions.items():
                packet = pack_header(GOODBYE, server_seq_num, sid)
                server_socket.sendto(packet, data['address'])
