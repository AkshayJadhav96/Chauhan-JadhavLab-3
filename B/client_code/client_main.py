import asyncio
import sys
from protocol.header import pack_header,unpack_header
from protocol import constants
from .client_proto import ClientProtocol
import time
import random

async def input_handler(protocol_instance):
    """A coroutine to handle keyboard input."""
    loop = asyncio.get_running_loop()
    while not protocol_instance.shutdown_event.is_set():
        if protocol_instance.state == 'READY':
            # Run the blocking readline() in a separate thread
            line = await loop.run_in_executor(None, sys.stdin.readline)

            if not line: # for end of file
                print("\n--- End of input detected (EOF). Sending GOODBYE. ---")
                protocol_instance.send_goodbye()

            line = line.strip()
            if sys.stdin.isatty() and line == 'q':
                print("\n--- 'q' detected. Sending GOODBYE. ---")
                protocol_instance.send_goodbye()
            else:
                protocol_instance.send_data(line)
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
