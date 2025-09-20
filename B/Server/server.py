#!/usr/bin/env python3
import socket
import sys
import threading
import queue # Use queue, not deque, for the multi-queue model
import time
import protocol

## --- Global Shared Resources ---
BUFFER_SIZE = 1024
server_seq_num = 0

num_worker_threads = 4
# A list of thread-safe queues, one for each worker. This is the only packet queue needed.
worker_queues = [queue.Queue() for _ in range(num_worker_threads)]
# The single dictionary for all session data, protected by a single lock.
sessions = {}
sessions_lock = threading.Lock()

def worker_thread(packet_queue, server_socket):
    """
    This is the consumer. It waits for packets on its DEDICATED queue.
    The lock is now only used for the shared 'sessions' dictionary.
    """
    global server_seq_num
    thread_id = threading.get_ident()

    while True:
        # ## FIX: This is now a simple, blocking get() from the worker's own queue.
        data, address = packet_queue.get()
        t1_ns = time.time_ns()

        header = protocol.unpack_header(data)
        
        if not header or header['magic'] != protocol.MAGIC_NUMBER or header['version'] != protocol.VERSION:
            continue
        
        t0_ns = header['timestamp']
        if t0_ns > 0:
            latency_ms = (t1_ns - t0_ns) / 1_000_000
            print(f"One-way latency: {latency_ms:.2f} ms")

        session_id = header['session_id']
        command = header['command']
        seq_num = header['sequence_number']
        
        reply_command = None
        reply_address = address
        
        reply_info = None

        ## NOTE: All access to the shared 'sessions' dictionary is protected by the single 'sessions_lock'.
        with sessions_lock:
            session = sessions.get(session_id)

            if not session:
                if command == protocol.HELLO:
                    sessions[session_id] = {
                        'address': address, 'expected_seq_num': 1,
                        'last_seen_time': time.time(),
                        'logical_clock': max(1, header['logical_clock']) + 1
                    }
                    print(f"0x{session_id:08x} [{seq_num}] Session created (Thread {thread_id})")
                    # reply_command = protocol.HELLO
                    reply_info = (protocol.HELLO,sessions[session_id]['logical_clock'])
            else: # Existing session
                session['logical_clock'] = max(session['logical_clock'], header['logical_clock']) + 1
                session['last_seen_time'] = time.time()

                if command == protocol.DATA:
                    expected = session['expected_seq_num']
                    if seq_num < expected - 1:
                        print(f"0x{session_id:08x} [{seq_num}] Protocol error: sequence number from the past. Closing.")
                        reply_info = (protocol.GOODBYE, session['logical_clock'])
                        del sessions[session_id]
                        reply_command = protocol.GOODBYE
                    elif seq_num == expected - 1:
                        print(f"0x{session_id:08x} [{seq_num}] Duplicate packet")
                        # No reply for duplicates
                    else: # Correct or lost packets
                        if seq_num > expected:
                            for i in range(expected, seq_num):
                                print(f"0x{session_id:08x} [{i}] Lost packet!")
                        
                        payload = data[protocol.HEADER_SIZE:].decode('utf-8').strip()
                        print(f"0x{session_id:08x} [{seq_num}] {payload}")
                        session['expected_seq_num'] = seq_num + 1
                        reply_info = (protocol.ALIVE, session['logical_clock'])
                
                elif command == protocol.GOODBYE:
                    print(f"0x{session_id:08x} [{seq_num}] GOODBYE from client.")
                    print(f"0x{session_id:08x} Session closed")
                    reply_info = (protocol.GOODBYE, session['logical_clock'])
                    del sessions[session_id]
                
                elif command == protocol.HELLO:
                    print(f"0x{session_id:08x} [{seq_num}] Protocol error: HELLO for existing session. Closing.")
                    reply_info = (protocol.GOODBYE, session['logical_clock'])
                    del sessions[session_id]
                
        if reply_info:
            reply_command, logical_clock = reply_info
            
            with sessions_lock:
                reply_seq = server_seq_num
                server_seq_num += 1
            
            # Increment logical clock for the "send" event
            logical_clock += 1
            current_ts = time.time_ns()
            
            reply_packet = protocol.pack_header(reply_command, reply_seq, session_id, clock=logical_clock, timestamp=current_ts)
            server_socket.sendto(reply_packet, address)

def session_cleaner(server_socket, timeout_seconds=30):
    global server_seq_num
    while True:
        time.sleep(5)
        now = time.time()
        timed_out_sessions = []
        with sessions_lock:
            for session_id, session_data in list(sessions.items()): # Iterate over a copy
                if now - session_data['last_seen_time'] > timeout_seconds:
                    timed_out_sessions.append((session_id, session_data['address']))
            for session_id, address in timed_out_sessions:
                print(f"0x{session_id:08x} Session timed out. Closing.")
                if session_id in sessions: del sessions[session_id]

        for session_id, address in timed_out_sessions:
            with sessions_lock:
                reply_seq = server_seq_num
                server_seq_num += 1
            goodbye_packet = protocol.pack_header(protocol.GOODBYE, reply_seq, session_id)
            server_socket.sendto(goodbye_packet, address)

def input_handler(shutdown_event):
    while not shutdown_event.is_set():
        try:
            command = sys.stdin.readline().strip()
            if command == 'q':
                print("Shutdown command received. Shutting down server...")
                shutdown_event.set()
                break
        except (KeyboardInterrupt, EOFError):
            print("\nShutdown command received. Shutting down server...")
            shutdown_event.set()
            break

def main():
    global server_seq_num
    if len(sys.argv) != 2:
        print("Usage: python3 server.py <portnum>")
        sys.exit(1)
    port = int(sys.argv[1])
    
    shutdown_event = threading.Event()
    
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
        server_socket.bind(('', port))
        server_socket.settimeout(1.0)
        print(f"Server listening on port {port}...")

        # ## FIX: Pass the correct arguments to each thread
        for i in range(num_worker_threads):
            worker = threading.Thread(target=worker_thread, args=(worker_queues[i], server_socket))
            worker.daemon = True
            worker.start()
        print(f"Started {num_worker_threads} worker threads.")

        cleaner = threading.Thread(target=session_cleaner, args=(server_socket,))
        cleaner.daemon = True
        cleaner.start()
        print("Started session cleaner thread.")

        input_thread = threading.Thread(target=input_handler, args=(shutdown_event,))
        input_thread.daemon = True
        input_thread.start()
        print("Started input handler thread. Type 'q' and press Enter to shut down.")

        # ## FIX: The corrected Producer Loop
        while not shutdown_event.is_set():
            try:
                data, address = server_socket.recvfrom(BUFFER_SIZE)
                header = protocol.unpack_header(data)
                if header:
                    session_id = header['session_id']
                    target_index = session_id % num_worker_threads
                    worker_queues[target_index].put((data, address))
            except socket.timeout:
                continue
        
        print("\nMain loop has exited. Sending GOODBYE to active clients...")
        with sessions_lock:
            for session_id, session_data in sessions.items():
                reply_seq = server_seq_num
                server_seq_num += 1
                goodbye_packet = protocol.pack_header(protocol.GOODBYE, reply_seq, session_id)
                server_socket.sendto(goodbye_packet, session_data['address'])
        
        print("Server has shut down.")

if __name__ == "__main__":
    main()
