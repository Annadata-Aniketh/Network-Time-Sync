import struct
# constants
MAGIC = b"NTPS"
VERSION = 1
PKT_TYPE_REQUEST = 1
PKT_TYPE_RESPONSE = 2
DEFAULT_PORT = 12300
PACKET_FORMAT = "!4sBHIddd" # !- Big Endian || 4s - Magic || B - Pkt type || H - Client id || I - Sequence no || ddd - t0, t1, t2
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)

class TimeSyncPacket:
    def __init__(self, pkt_type: int, client_id: int, seq_num: int, t0: float = 0.0, t1: float = 0.0, t2: float = 0.0):
        self.pkt_type = pkt_type
        self.client_id = client_id
        self.seq_num = seq_num
        self.t0 = t0
        self.t1 = t1
        self.t2 = t2
    def to_bytes(self) -> bytes:
        return struct.pack(
            PACKET_FORMAT,
            MAGIC,
            self.pkt_type,
            self.client_id,
            self.seq_num,
            self.t0,
            self.t1,
            self.t2
        )

    def __repr__(self) -> str:
        type_str = "REQUEST" if self.pkt_type == PKT_TYPE_REQUEST else ("RESPONSE" if self.pkt_type == PKT_TYPE_RESPONSE else f"TYPE_{self.pkt_type}")
        return (
            f"TimeSyncPacket(type={type_str}, client_id={self.client_id}, "
            f"seq={self.seq_num}, t0={self.t0:.6f}, t1={self.t1:.6f}, t2={self.t2:.6f})"
        )
    @classmethod
    def from_bytes(cls, data: bytes) -> "TimeSyncPacket":
        if len(data) != PACKET_SIZE:
            raise ValueError(f"Packet size mismatch: expected {PACKET_SIZE}, got {len(data)}")
        
        magic, pkt_type, client_id, seq_num, t0, t1, t2 = struct.unpack(PACKET_FORMAT, data)
        
        if magic != MAGIC:
            raise ValueError(f"Invalid magic number: {magic!r}, expected {MAGIC!r}")
            
        return cls(pkt_type, client_id, seq_num, t0, t1, t2)

# Mathematical calculations
def calculate_delay(t0: float, t1: float, t2: float, t3: float):
    delay = (t3 - t0) - (t2 - t1)
    return delay
def calculate_offset(t0: float, t1: float, t2: float, t3: float):
    offset = ((t1-t0)+(t2-t3))/2.0
    return offset

