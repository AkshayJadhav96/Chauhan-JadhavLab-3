import time
import threading
import queue
from protocol.constants import HELLO, DATA, ALIVE, GOODBYE, MAGIC_NUMBER, VERSION
from protocol.header import unpack_header, pack_header
from protocol.utils import print_latency
from .session import sessions, sessions_lock, server_seq_num

def worker_thread(packet_queue, server_socket):
    global server_seq_num
    thread_id = threading.get_ident()

    while True:
        data, address = packet_queue.get()
        t1_ns = time.time_ns()

        header = unpack_header(data)
        if not header or header['magic'] != MAGIC_NUMBER or header['version'] != VERSION:
            continue

        print_latency(header['timestamp'], t1_ns)

        session_id = header['session_id']
        command = header['command']
        seq_num = header['sequence_number']
        reply_info = None

        with sessions_lock:
            session = sessions.get(session_id)
            if not session:
                if command == HELLO:
                    sessions[session_id] = {
                        'address': address, 'expected_seq_num': 1,
                        'last_seen_time': time.time(),
                        'logical_clock': max(1, header['logical_clock']) + 1
                    }
                    print(f"0x{session_id:08x} [{seq_num}] Session created (Thread {thread_id})")
                    reply_info = (HELLO, sessions[session_id]['logical_clock'])
            else:
                session['logical_clock'] = max(session['logical_clock'], header['logical_clock']) + 1
                session['last_seen_time'] = time.time()

                if command == DATA:
                    expected = session['expected_seq_num']
                    if seq_num < expected - 1:
                        print(f"0x{session_id:08x} [{seq_num}] Protocol error: old sequence. Closing.")
                        reply_info = (GOODBYE, session['logical_clock'])
                        del sessions[session_id]
                    elif seq_num == expected - 1:
                        print(f"0x{session_id:08x} [{seq_num}] Duplicate packet")
                    else:
                        if seq_num > expected:
                            for i in range(expected, seq_num):
                                print(f"0x{session_id:08x} [{i}] Lost packet!")
                        payload = data[28:].decode('utf-8').strip()
                        print(f"0x{session_id:08x} [{seq_num}] {payload}")
                        session['expected_seq_num'] = seq_num + 1
                        reply_info = (ALIVE, session['logical_clock'])

                elif command == GOODBYE:
                    print(f"0x{session_id:08x} [{seq_num}] GOODBYE from client.")
                    print(f"0x{session_id:08x} Session closed")
                    reply_info = (GOODBYE, session['logical_clock'])
                    del sessions[session_id]

                elif command == HELLO:
                    print(f"0x{session_id:08x} [{seq_num}] Protocol error: HELLO on existing session.")
                    reply_info = (GOODBYE, session['logical_clock'])
                    del sessions[session_id]

        if reply_info:
            reply_command, logical_clock = reply_info
            with sessions_lock:
                reply_seq = server_seq_num
                server_seq_num += 1
            logical_clock += 1
            reply_packet = pack_header(reply_command, reply_seq, session_id,
                                       clock=logical_clock, timestamp=time.time_ns())
            server_socket.sendto(reply_packet, address)

def start_workers(server_socket, num_workers=4):
    queues = [queue.Queue() for _ in range(num_workers)]
    for q in queues:
        t = threading.Thread(target=worker_thread, args=(q, server_socket), daemon=True)
        t.start()
    print(f"Started {num_workers} worker threads.")
    return queues
