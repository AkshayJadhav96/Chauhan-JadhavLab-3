#!/usr/bin/env python3
import time
from protocol import constants
from protocol.header import pack_header,unpack_header

class ClientProtocol:
    def __init__(self, loop, session_id,shutdown_event):
        self.loop = loop
        self.session_id = session_id
        self.shutdown_event = shutdown_event
        self.transport = None
        self.client_seq_num = 0
        self.client_lc = 0
        self.state = 'HELLO_WAIT'
        self.timeout_handle = None
    
    def send_hello(self):
        if self.timeout_handle:
            self.timeout_handle.cancel()
        self.client_lc+=1
        hello_packet = pack_header(
            constants.HELLO, self.client_seq_num, self.session_id, 
            clock=self.client_lc, timestamp=time.time_ns()
        )
        self.transport.sendto(hello_packet)
        self.client_seq_num += 1

        self.timeout_handle = self.loop.call_later(5, self._handle_timeout)

    def send_goodbye(self):
        if self.timeout_handle:
            self.timeout_handle.cancel()
        self.client_lc+=1
        goodbye_packet = pack_header(
            constants.GOODBYE, self.client_seq_num,
            self.session_id, clock=self.client_lc,
            timestamp=time.time_ns()
        )
        self.transport.sendto(goodbye_packet)
        self.client_seq_num += 1

        # Change state and set a timeout for the final GOODBYE reply
        self.state = 'CLOSING'
        self.timeout_handle = self.loop.call_later(5, self._handle_timeout)

    def send_data(self,line):
        if self.timeout_handle:
            self.timeout_handle.cancel()
        self.client_lc += 1
        
        # Pack and send the DATA message
        data_header = pack_header(
            constants.DATA, self.client_seq_num, 
            self.session_id, clock=self.client_lc, 
            timestamp=time.time_ns()
        )
        payload = line.encode('utf-8')
        self.transport.sendto(data_header + payload)
        
        print(f"-----> Sent DATA packet #{self.client_seq_num}")
        self.client_seq_num += 1

        self.state = 'READY_TIMER'
        self.timeout_handle = self.loop.call_later(5, self._handle_timeout)

    def connection_made(self, transport):
        """Called by the event loop when the socket is ready."""
        self.transport = transport
        print(f"--- Sending HELLO (SID=0x{self.session_id:08x}) ---")
        self.send_hello()

        # self.client_lc += 1
        # The first thing we do is send a HELLO packet
        # hello_packet = pack_header(
        #     constants.HELLO, self.client_seq_num, self.session_id, 
        #     clock=self.client_lc, timestamp=time.time_ns()
        # )
        # self.transport.sendto(hello_packet)
        # self.client_seq_num += 1

        # self.timeout_handle = self.loop.call_later(5, self._handle_timeout)

    def datagram_received(self, data, addr):
        """Called by the event loop when a packet is received."""
        header = unpack_header(data)
        if not header:
            print("<----- Received malformed packet.")
            return

        # Look up the command name for cleaner printing
        command_name = "UNKNOWN"
        if header['command'] < len(constants.COMMAND_NAMES):
            command_name = constants.COMMAND_NAMES[header['command']]
        
        self.client_lc = max(self.client_lc, header['logical_clock']) + 1
        # print(f"Client LC updated to: {self.client_lc}")

        if self.state=='HELLO_WAIT' and header['command'] == constants.HELLO:
            if self.timeout_handle:
                self.timeout_handle.cancel()
            
            self.state = "READY"
            print(f"--- Handshake complete. Received {command_name} from server (Seq: {header['sequence_number']}, LC: {header['logical_clock']}) ---")
        
        elif self.state == 'READY_TIMER' and header['command'] == constants.ALIVE:
            # If we get the ALIVE reply, cancel the timeout and go back to READY
            if self.timeout_handle:
                self.timeout_handle.cancel()
            self.state = 'READY'
            print(f"<----- Received {command_name}. Server acknowledged data.")

        elif self.state == 'CLOSING' and header['command'] == constants.GOODBYE:
            # This is the final reply from the server. We can now close.
            if self.timeout_handle:
                self.timeout_handle.cancel()
            print(f"<----- Received final {command_name}. Client shutting down.")
            self.transport.close() # This will trigger connection_lost and stop the loop
        
        elif header['command'] == constants.GOODBYE:
            # This is the final reply from the server. We can now close.
            if self.timeout_handle:
                self.timeout_handle.cancel()
            print(f"<----- Received unexpected {command_name}. Client shutting down.")
            self.transport.close() # This will trigger connection_lost and stop the loop
    
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
        if self.state in ('HELLO_WAIT', 'READY_TIMER','READY'):
            print(f"--- Timeout! No reply from server while in state {self.state}. Sending GOODBYE. ---")
            # Instead of closing directly, initiate the proper shutdown sequence.
            self.send_goodbye() 
        elif self.state == 'CLOSING':
            # If we time out waiting for the final GOODBYE, then we can close.
            print(f"--- Timeout! No final GOODBYE from server. Closing connection. ---")
            self.transport.close()
            