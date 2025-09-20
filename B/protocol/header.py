import struct
from .constants import MAGIC_NUMBER, VERSION, HEADER_FORMAT, HEADER_SIZE

def pack_header(command, seq_num, session_id, clock=0, timestamp=0):
    """Packs a UAP header into bytes."""
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
    """Unpacks a UAP header into a dict, or None if invalid/too short."""
    if len(data) < HEADER_SIZE:
        return None
    fields = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
    return {
        'magic': fields[0],
        'version': fields[1],
        'command': fields[2],
        'sequence_number': fields[3],
        'session_id': fields[4],
        'logical_clock': fields[5],
        'timestamp': fields[6],
    }
