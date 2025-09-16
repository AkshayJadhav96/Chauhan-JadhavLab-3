import socket
import sys
import random
import time
import protocol

BUFFER_SIZE = 1024

def main():
    """
    A simple, synchronous client to test the server's full functionality.
    """
    if len(sys.argv) != 3:
        print("Usage: python3 test_client.py <hostname> <portnum>")
        sys.exit(1)
    
    hostname = sys.argv[1]
    port = int(sys.argv[2])
    server_address = (hostname, port)

    # Initialize client state
    session_id = random.randint(0, 0xFFFFFFFF)
    client_seq_num = 0
    client_lc = 0

    # Create a socket and set a timeout
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(5.0) # 5 second timeout

        def receive_and_print():
            """Helper function to wait for a reply and print it."""
            nonlocal client_lc
            try:
                data, address = s.recvfrom(BUFFER_SIZE)
                header = protocol.unpack_header(data)
                if header:
                    print("<- Received reply from server:")
                    print(f"   {header}")
                    # Update logical clock based on server's reply
                    client_lc = max(client_lc, header['logical_clock']) + 1
                    print(f"   Client LC updated to: {client_lc}")
                else:
                    print("<- Received malformed packet.")
            except socket.timeout:
                print("<- No reply from server; timed out.")

        try:
            # --- Step 1: Send HELLO ---
            print(f"\n--- Step 1: Sending HELLO (SID=0x{session_id:08x}) ---")
            client_lc += 1; print(f"Client LC is now: {client_lc}")
            hello_packet = protocol.pack_header(
                protocol.HELLO, client_seq_num, session_id, clock=client_lc, timestamp=time.time_ns()
            )
            s.sendto(hello_packet, server_address)
            client_seq_num += 1
            receive_and_print()

            # --- Step 2: Send first DATA packet ---
            print("\n--- Step 2: Sending DATA ---")
            client_lc += 1; print(f"Client LC is now: {client_lc}")
            data_header = protocol.pack_header(
                protocol.DATA, client_seq_num, session_id, clock=client_lc, timestamp=time.time_ns()
            )
            payload = b"Hello from the test client!"
            s.sendto(data_header + payload, server_address)
            client_seq_num += 1
            receive_and_print()

            # --- Step 3: Send second DATA packet ---
            time.sleep(1) # Wait a second
            print("\n--- Step 3: Sending more DATA ---")
            client_lc += 1; print(f"Client LC is now: {client_lc}")
            data_header_2 = protocol.pack_header(
                protocol.DATA, client_seq_num, session_id, clock=client_lc, timestamp=time.time_ns()
            )
            payload_2 = b"This is the second message."
            s.sendto(data_header_2 + payload_2, server_address)
            client_seq_num += 1
            receive_and_print()

            # --- Step 4: Send GOODBYE ---
            time.sleep(1)
            print("\n--- Step 4: Sending GOODBYE ---")
            client_lc += 1; print(f"Client LC is now: {client_lc}")
            goodbye_packet = protocol.pack_header(
                protocol.GOODBYE, client_seq_num, session_id, clock=client_lc, timestamp=time.time_ns()
            )
            s.sendto(goodbye_packet, server_address)
            receive_and_print()

        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()