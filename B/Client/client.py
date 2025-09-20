#!/usr/bin/env python3
import asyncio
import socket
import sys
import random
import time
import protocol

class ClientProtocol:
    def __init__(self, loop, session_id,shutdown_event):
        self.loop = loop
        self.session_id = session_id
        self.shutdown_event = shutdown_event
        self.transport = None
        self.client_seq_num = 0
        self.client_lc = 0
        self.state = 'WAITING_FOR_HELLO'
        self.timeout_handle = None

    def connection_made(self, transport):
        """Called by the event loop when the socket is ready."""
        self.transport = transport
        print(f"--- Sending HELLO (SID=0x{self.session_id:08x}) ---")
        self.client_lc += 1
        
        # The first thing we do is send a HELLO packet
        hello_packet = protocol.pack_header(
            protocol.HELLO, self.client_seq_num, self.session_id, 
            clock=self.client_lc, timestamp=time.time_ns()
        )
        self.transport.sendto(hello_packet)
        self.client_seq_num += 1

        self.timeout_handle = self.loop.call_later(5, self._handle_timeout)

    def datagram_received(self, data, addr):
        """Called by the event loop when a packet is received."""
        header = protocol.unpack_header(data)
        if not header:
            print("<----- Received malformed packet.")
            return

        # Look up the command name for cleaner printing
        command_name = "UNKNOWN"
        if header['command'] < len(protocol.COMMAND_NAMES):
            command_name = protocol.COMMAND_NAMES[header['command']]
        
        self.client_lc = max(self.client_lc, header['logical_clock']) + 1
        # print(f"Client LC updated to: {self.client_lc}")

        if self.state=='WAITING_FOR_HELLO' and header['command'] == protocol.HELLO:
            if self.timeout_handle:
                self.timeout_handle.cancel()
            
            self.state = "READY"
            print(f"--- Handshake complete. Client is READY. Received {command_name} from server (Seq: {header['sequence_number']}, LC: {header['logical_clock']}) ---")
        
        elif self.state == 'WAITING_FOR_ALIVE' and header['command'] == protocol.ALIVE:
            # If we get the ALIVE reply, cancel the timeout and go back to READY
            if self.timeout_handle:
                self.timeout_handle.cancel()
        
            self.state = 'READY'
            print(f"<----- Received {command_name}. Server acknowledged data. Client is READY.")

        elif self.state == 'CLOSING' and header['command'] == protocol.GOODBYE:
            # This is the final reply from the server. We can now close.
            if self.timeout_handle:
                self.timeout_handle.cancel()
            print(f"<----- Received final {command_name}. Client shutting down.")
            self.transport.close() # This will trigger connection_lost and stop the loop

        elif header['command'] == protocol.GOODBYE:
            print(f"<----- Received {command_name}. Server is closing the session. Exiting.")
            self.shutdown_event.set()  
    
    def error_received(self, exc):
        """Called by the event loop on a socket error."""
        print(f"Error received: {exc}")
        self.shutdown_event.set()

    def connection_lost(self, exc):
        """Called by the event loop when the connection is closed."""
        print("Connection closed.")
        self.shutdown_event.set()
    
    def _handle_timeout(self):
        # Check if we are still in the state we set the timer for
        if self.state in ('WAITING_FOR_HELLO', 'WAITING_FOR_ALIVE', 'CLOSING'):
            print(f"--- Timeout! No reply from server while in state {self.state}. ---")
            self.transport.close() # This will trigger connection_lost

async def input_handler(protocol_instance):
    """A coroutine to handle keyboard input."""
    loop = asyncio.get_running_loop()
    while not protocol_instance.shutdown_event.is_set():
        if protocol_instance.state == 'READY':
            # Run the blocking readline() in a separate thread
            line = await loop.run_in_executor(None, sys.stdin.readline)

            if not line: # for end of file
                print("\n--- End of input detected (EOF). Sending GOODBYE. ---")
                protocol_instance.client_lc += 1
        
                goodbye_packet = protocol.pack_header(
                    protocol.GOODBYE, protocol_instance.client_seq_num,
                    protocol_instance.session_id, clock=protocol_instance.client_lc,
                    timestamp=time.time_ns()
                )
                protocol_instance.transport.sendto(goodbye_packet)
                protocol_instance.client_seq_num += 1

                # Change state and set a timeout for the final GOODBYE reply
                protocol_instance.state = 'CLOSING'
                protocol_instance.timeout_handle = protocol_instance.loop.call_later(5, protocol_instance._handle_timeout)
                # break

            line = line.strip()
            if sys.stdin.isatty() and line == 'q':
                print("\n--- 'q' detected. Sending GOODBYE. ---")
                # This is the same GOODBYE logic
                protocol_instance.client_lc += 1
                goodbye_packet = protocol.pack_header(
                    protocol.GOODBYE, protocol_instance.client_seq_num,
                    protocol_instance.session_id, clock=protocol_instance.client_lc,
                    timestamp=time.time_ns()
                )
                protocol_instance.transport.sendto(goodbye_packet)
                protocol_instance.state = 'CLOSING'
                protocol_instance.timeout_handle = protocol_instance.loop.call_later(5, protocol_instance._handle_timeout)
                # break # Exit the input handler loop

            else:
                # Increment logical clock for the stdin event
                protocol_instance.client_lc += 1
                
                # Pack and send the DATA message
                data_header = protocol.pack_header(
                    protocol.DATA, protocol_instance.client_seq_num, 
                    protocol_instance.session_id, clock=protocol_instance.client_lc, 
                    timestamp=time.time_ns()
                )
                payload = line.encode('utf-8')
                protocol_instance.transport.sendto(data_header + payload)
                
                print(f"-----> Sent DATA packet #{protocol_instance.client_seq_num}")
                protocol_instance.client_seq_num += 1

                protocol_instance.state = 'WAITING_FOR_ALIVE'
                protocol_instance.timeout_handle = protocol_instance.loop.call_later(5, protocol_instance._handle_timeout)
        else:
            await asyncio.sleep(0)


async def main():
    if len(sys.argv) != 3:
        print("Usage: python3 client.py <hostname> <portnum>")
        sys.exit(1)
    
    hostname = sys.argv[1]
    port = int(sys.argv[2])
    
    loop = asyncio.get_running_loop()
    session_id = random.randint(0, 0xFFFFFFFF)
    shutdown_event = asyncio.Event()
    
    # Create the UDP endpoint. This starts the network listening.
    transport, protocol_instance = await loop.create_datagram_endpoint(
        lambda: ClientProtocol(loop, session_id, shutdown_event),
        remote_addr=(hostname, port)
    )

    # Create two main tasks that will run concurrently
    input_task = asyncio.create_task(input_handler(protocol_instance))
    shutdown_task = asyncio.create_task(shutdown_event.wait())

    # Wait for either the input handler to finish or the shutdown event to be set
    await asyncio.wait([input_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED)

    transport.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
