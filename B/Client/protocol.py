import struct

# Protocol constants from the lab document
MAGIC_NUMBER = 0xC461      
VERSION = 1                

# Command Types
HELLO = 0              
DATA = 1               
ALIVE = 2              
GOODBYE = 3   

COMMAND_NAMES = ('HELLO', 'DATA', 'ALIVE', 'GOODBYE')

# This format string tells Python how to pack/unpack the header.
# > = Big-endian (network byte order)
# H = Unsigned Short (2 bytes for magic)
# B = Unsigned Byte (1 byte for version, 1 for command)
# I = Unsigned Int (4 bytes for sequence, 4 for session)
# Q = Unsigned Long Long (8 bytes for clock, 8 for timestamp)
HEADER_FORMAT = '>HBBIIQQ'  

# Calculate the exact size of the header based on the format string.
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


def pack_header(command, seq_num, session_id, clock=0, timestamp=0):
    """Packs the UAP header into a bytes object."""
    
    return struct.pack(
        HEADER_FORMAT,
        MAGIC_NUMBER,
        VERSION,
        command,
        seq_num,
        session_id,
        clock,
        timestamp
    )

def unpack_header(data):
    """Unpacks the UAP header from a bytes object and returns a dictionary."""
    # First, check if we have enough data to even contain a header
    if len(data) < HEADER_SIZE:
        return None
    
    # Unpack the first part of the data according to the format string
    # This returns a tuple of values.
    header_tuple = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
    
    header_dict = {
        'magic': header_tuple[0],
        'version': header_tuple[1],
        'command': header_tuple[2],
        'sequence_number': header_tuple[3],
        'session_id': header_tuple[4],
        'logical_clock': header_tuple[5],
        'timestamp': header_tuple[6]
    }
    return header_dict

