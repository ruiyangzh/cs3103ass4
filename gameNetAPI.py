import socket
import time
import struct

# Header: ChannelType (1B), isAck (1B), SeqNo (2B), Timestamp (4B)
HEADER_FMT = "!BBHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

CHANNEL_RELIABLE = 0
CHANNEL_UNRELIABLE = 1

DEFAULT_TIMEOUT_MS = 200
DEFAULT_WINDOW = 32

def now_ms():
    return int(time.time() * 1000) & 0xFFFFFFFF  # 32-bit timestamp

def pack_packet(channel_type: int, isack:bool, seqno: int, timestamp_ms: int, payload: bytes):
    return struct.pack(HEADER_FMT, channel_type, isack, seqno, timestamp_ms) + payload

def unpack_packet(packet: bytes):
    channel_type, isack, seqno, timestamp_ms, payload = struct.unpack(HEADER_FMT, packet)
    return channel_type, isack, seqno, timestamp_ms, payload

class gameNetAPI:

    def __init__(self, local, remote): #local and remote are tuples
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local)
        self.seq_no = 0
        self.remote = remote
        

    def send_packet(self, packet, is_reliable):
        if is_reliable:
            self.send_reliable(packet)
        else:
            self.send_unreliable(packet)
        

    def send_unreliable(self, payload):
        pkt = pack_packet(CHANNEL_UNRELIABLE, False, 0, now_ms(), payload)
        self.sock.sendto(pkt, self.remote)

    def send_reliable(self, payload):
        reply_recieved = None
        t = time.time()
        pkt = pack_packet(CHANNEL_RELIABLE, False, self.seq_no, now_ms(), payload)
        while not reply_recieved and time.time() - t < 0.2:
            self.sock.sendto(pkt, self.remote)
            reply_recieved = recieve_ack(seq_no)
        self.seq_no += 1

    def send_ack(self, packet):
        _, _, seqno,_,_ = unpack_packet(packet)
        pkt = pack_packet(CHANNEL_UNRELIABLE, True, seqno, now_ms(), '')
        self.sock.sendto(pkt, self.remote)
            
    def recieve_packet(self):
        packet, addr = self.sock.recvfrom(1024)
        channel_type, seqno, timestamp_ms, payload = unpack_packet(packet)
        if channel_type == CHANNEL_UNRELIABLE:
            pass
        else:
            #do something with buffers
            self.send_ack(packet)
        return seqno, channel_type, timestamp_ms, retransmissions, packet_arrivals #can we just compute rtt as 2 * (time.time() - timestamp_ms)?
#         should return SeqNo, ChannelType, Timestamp, retransmissions, packet arrivals and RTT, for use in server to print logs


        # print(f"Received message from {addr}: {(payload)} with seqno {seqno} and timestamp {timestamp_ms}")
        
