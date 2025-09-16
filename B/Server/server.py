import socket
import sys
import threading
from collections import deque # Import deque
import protocol
import time

# A constant for the maximum size of a UDP packet
BUFFER_SIZE = 1024
server_seq_num = 0

def worker_thread(packet_deque, sessions, lock, condition, server_socket):
    """
    This is the consumer. It waits for packets on the deque and processes them.
    """
    global server_seq_num
    thread_id = threading.get_ident() # Get a unique ID for this thread for printing
    print(f"Worker thread {thread_id} started.")

    while True:
        t1_ns = time.time_ns()
        with lock:
            # Wait until the deque is not empty
            while not packet_deque:
                condition.wait()  # Go to sleep and wait for a signal
            
            # THE KEY CHANGE: Use popleft() for efficient FIFO removal
            data, address = packet_deque.popleft()

        # Now that we are outside the lock, we can do the slow processing.
        header = protocol.unpack_header(data)
        
        # Validate the header
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
        print(f"Thread {thread_id}: Received packet for session 0x{session_id:08x}")
        
        with lock:
            session = sessions.get(session_id)

            if not session:
                if command == protocol.HELLO:
                    print(f"0x{session_id:08x} [{seq_num}] Session created")
                    sessions[session_id] = {
                        'address': address,
                        'expected_seq_num': 1,
                        'last_seen_time': time.time(),
                        'logical_clock': max(1, header['logical_clock']) + 1
                    }
                    reply_command = protocol.HELLO
                else:
                    continue 
            else:
                session['logical_clock'] = max(session['logical_clock'], header['logical_clock']) + 1
                session['last_seen_time'] = time.time()

                if command == protocol.DATA:
                    expected = session['expected_seq_num']
                    if seq_num < expected - 1:
                        print(f"0x{session_id:08x} [{seq_num}] Protocol error: sequence number from the past. Closing.")
                        del sessions[session_id]
                        reply_command = protocol.GOODBYE

                    elif seq_num==expected-1:
                        print(f"0x{session_id:08x} [{seq_num}] Duplicate packet")

                    elif seq_num > expected:
                        for i in range(session['expected_seq_num'], seq_num):
                            print(f"0x{session_id:08x} [{i}] Lost packet!")
                        session['expected_seq_num'] = seq_num+1
                    else:
                        payload = data[protocol.HEADER_SIZE:].decode('utf-8').strip()
                        print(f"0x{session_id:08x} [{seq_num}] {payload}")
                        session['expected_seq_num'] += 1
                    
                    reply_command = protocol.ALIVE
                
                elif command == protocol.GOODBYE:
                    print(f"0x{session_id:08x} [{seq_num}] GOODBYE from client.")
                    print(f"0x{session_id:08x} Session closed")
                    del sessions[session_id]
                    reply_command = protocol.GOODBYE
                
                elif command == protocol.HELLO:
                    print(f"0x{session_id:08x} [{seq_num}] Protocol error: HELLO received for existing session. Closing.")
                    del sessions[session_id]
                    reply_command = protocol.GOODBYE
                
        if reply_command is not None:
            session_data = sessions.get(session_id)
            if session_data:
                # --- LOGICAL CLOCK & TIMESTAMP: Prepare to send ---
                session_data['logical_clock'] += 1 # Increment clock for the "send" event
                current_lc = session_data['logical_clock']
                current_ts = time.time_ns()
                with lock:
                    reply_seq = server_seq_num
                    server_seq_num+=1
                reply_packet = protocol.pack_header(reply_command, reply_seq, session_id, clock=current_lc, timestamp=current_ts)
                server_socket.sendto(reply_packet, address)

def session_cleaner(sessions, lock, server_socket, timeout_seconds=30):
    """Periodically checks for and removes inactive sessions."""
    global server_seq_num
    while True:
        time.sleep(5) # Check every 5 seconds

        now = time.time()
        timed_out_sessions = []

        with lock:
            # Find timed out sessions
            for session_id, session_data in sessions.items():
                if now - session_data['last_seen_time'] > timeout_seconds:
                    timed_out_sessions.append((session_id, session_data['address']))

            # Remove them from the dictionary
            for session_id, address in timed_out_sessions:
                print(f"0x{session_id:08x} Session timed out. Closing.")
                del sessions[session_id]

        # Send GOODBYE messages outside the lock
        for session_id, address in timed_out_sessions:
            with lock:
                reply_seq = server_seq_num
                server_seq_num = server_seq_num+1
            goodbye_packet = protocol.pack_header(protocol.GOODBYE, server_seq_num, session_id)
            server_socket.sendto(goodbye_packet, address)

def input_handler(shutdown_event):
    """A dedicated thread to listen for user input to shut down."""

    while not shutdown_event.is_set():
        try:
            # This line will block until the user presses Enter
            command = sys.stdin.readline().strip()
            if command == 'q':
                print("Shutdown command received. Shutting down server...")
                shutdown_event.set()
                break
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            print("Shutdown command received (Ctrl+C). Shutting down server...")
            shutdown_event.set()
            break

def main():
    """
    This is the producer. It sets up the server, starts the workers, 
    and listens for all incoming packets.
    """
    global server_seq_num
    if len(sys.argv) != 2:
        print("Usage: python3 server.py <portnum>")
        sys.exit(1)
    
    port = int(sys.argv[1])
    
    # 1. Create shared resources
    packet_deque = deque() # Use deque instead of a list
    sessions = {}
    lock = threading.Lock()
    condition = threading.Condition(lock)
    shutdown_event = threading.Event()
    

    # 2. Create and bind the main UDP socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
        server_socket.bind(('', port))
        server_socket.settimeout(1.0)
        print(f"Server listening on port {port}...")

        # 3. Create and start a pool of worker threads
        num_worker_threads = 4
        for i in range(num_worker_threads):
            worker = threading.Thread(
                target=worker_thread,
                args=(packet_deque,sessions, lock, condition, server_socket)
            )
            worker.daemon = True
            worker.start()
        print(f"Started {num_worker_threads} worker threads.")

        cleaner = threading.Thread(target=session_cleaner,
                                    args=(sessions, lock, server_socket))
        cleaner.daemon = True
        cleaner.start()
        print("Started session cleaner thread.")

        input_thread = threading.Thread(target=input_handler, args=(shutdown_event,))
        input_thread.daemon = True
        input_thread.start()
        print("Started input handler thread. Type 'q' and press Enter to shut down.")

        # 4. The Producer Loop
        while not shutdown_event.is_set():
            try:
                data, address = server_socket.recvfrom(BUFFER_SIZE)
                with lock:
                    packet_deque.append((data, address)) # Add packet to the deque
                    condition.notify() # Wake up one worker
            except socket.timeout:
                continue
        
         # 5. After the loop ends, send GOODBYE to all active clients
        print("Main loop has exited. Sending GOODBYE to active clients...")
        with lock:
            for session_id, session_data in sessions.items():
                with lock:
                    reply_seq = server_seq_num
                    server_seq_num = server_seq_num+1
                goodbye_packet = protocol.pack_header(protocol.GOODBYE, reply_seq, session_id)
                server_socket.sendto(goodbye_packet, session_data['address'])
        
        print("Server has shut down.")

if __name__ == "__main__":
    main()
