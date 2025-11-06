# gamenet_api.py
import socket
import struct
import time
import threading
import logging
import queue

# Header: ChannelType (1B), SeqNo (2B), Timestamp (4B)
HEADER_FMT = "!BHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

CHANNEL_RELIABLE = 0
CHANNEL_UNRELIABLE = 1
CHANNEL_ACK = 2

DEFAULT_TIMEOUT_MS = 200
DEFAULT_WINDOW = 32

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def now_ms():
    return int(time.time() * 1000)  # 32-bit timestamp

def pack_packet(channel_type: int, seqno: int, timestamp_ms: int, payload: bytes) -> bytes:
    return struct.pack(HEADER_FMT, channel_type, seqno, timestamp_ms) + payload

def unpack_packet(data: bytes):
    if len(data) < HEADER_SIZE:
        raise ValueError("Packet too small")
    channel_type, seqno, timestamp_ms = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    payload = data[HEADER_SIZE:]
    return channel_type, seqno, timestamp_ms, payload

class Metrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.sent_bytes = 0
        self.recv_bytes = 0
        self.sent_packets = 0
        self.recv_packets = 0
        self.retransmissions = 0
        self.rtts = []
        self.jitter = 0.0
        self.prev_transit = None

    def add_sent(self, size):
        with self.lock:
            self.sent_bytes += size
            self.sent_packets += 1

    def add_recv(self, size):
        with self.lock:
            self.recv_bytes += size
            self.recv_packets += 1

    def add_retrans(self):
        with self.lock:
            self.retransmissions += 1

    def add_rtt(self, rtt_ms):
        with self.lock:
            self.rtts.append(rtt_ms)

    def update_jitter(self, arrival_ms, ts_ms):
        transit = arrival_ms - ts_ms
        if self.prev_transit is None:
            self.prev_transit = transit
            return
        d = abs(transit - self.prev_transit)
        self.prev_transit = transit
        self.jitter += (d - self.jitter) / 16.0

    def snapshot(self):
        with self.lock:
            avg_rtt = sum(self.rtts)/len(self.rtts) if self.rtts else None
            return {
                "sent_bytes": self.sent_bytes,
                "recv_bytes": self.recv_bytes,
                "sent_packets": self.sent_packets,
                "recv_packets": self.recv_packets,
                "retransmissions": self.retransmissions,
                "avg_rtt_ms": avg_rtt,
                "jitter_ms": self.jitter
            }


class ReliableSender:
    def __init__(self, sock, remote_addr, timeout_ms=DEFAULT_TIMEOUT_MS, window=DEFAULT_WINDOW, metrics=None):
        self.sock = sock
        self.remote = remote_addr
        self.timeout_ms = timeout_ms
        self.window = window
        self.send_lock = threading.Lock()
        self.next_seq = 0
        self.outstanding = {}  # seq -> (pkt_bytes, ts_sent, attempts)
        self.metrics = metrics or Metrics()
        self.running = True
        self.timers_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self.timers_thread.start()

    def _timer_loop(self):
        while self.running:
            now = now_ms()
            to_retrans = []
            with self.send_lock:
                for seq, (pkt, ts_sent, attempts) in list(self.outstanding.items()):
                    if now - ts_sent >= self.timeout_ms:
                        to_retrans.append(seq)
            for seq in to_retrans:
                self._retransmit(seq)
            time.sleep(self.timeout_ms/1000/4)

    def send_reliable(self, payload: bytes):
        with self.send_lock:
            while len(self.outstanding) >= self.window:
                self.send_lock.release()
                time.sleep(0.005)
                self.send_lock.acquire()
            seq = self.next_seq % 65536
            ts = now_ms()
            pkt = pack_packet(CHANNEL_RELIABLE, seq, ts, payload)
            self.sock.sendto(pkt, self.remote)
            self.metrics.add_sent(len(pkt))
            self.outstanding[seq] = (pkt, ts, 1)
            self.next_seq += 1
            return seq

    def _retransmit(self, seq):
        with self.send_lock:
            if seq not in self.outstanding:
                return
            pkt, ts_sent, attempts = self.outstanding[seq]
            logging.info(f"Retransmitting seq={seq} attempt={attempts+1}")
            try:
                self.sock.sendto(pkt, self.remote)
                self.metrics.add_sent(len(pkt))
                self.metrics.add_retrans()
            except Exception:
                pass
            self.outstanding[seq] = (pkt, now_ms(), attempts+1)

    def handle_ack(self, ack_seq):
        with self.send_lock:
            if ack_seq in self.outstanding:
                pkt, ts_sent, attempts = self.outstanding.pop(ack_seq)
                rtt = now_ms() - ts_sent
                self.metrics.add_rtt(rtt)
                logging.info(f"ACK received seq={ack_seq} RTT={rtt}ms attempts={attempts}")

    def stop(self):
        self.running = False
        self.timers_thread.join(timeout=1.0)


class ReliableReceiver:
    def __init__(self, sock, metrics=None):
        self.sock = sock
        self.metrics = metrics or Metrics()
        self.recv_lock = threading.Lock()
        self.expected_seq = 0
        self.buffer = {}
        self.all_packets = queue.Queue()  # store both reliable and unreliable

    def handle_packet(self, data, addr):
        try:
            channel, seq, ts, payload = unpack_packet(data)
            self.metrics.add_recv(len(data))
            if channel == CHANNEL_RELIABLE:
                # send ACK
                ack_pkt = pack_packet(CHANNEL_ACK, seq, ts, b'')
                self.sock.sendto(ack_pkt, addr)
                with self.recv_lock:
                    if seq == self.expected_seq:
                        self.all_packets.put(payload)
                        self.expected_seq += 1
                        while self.expected_seq in self.buffer:
                            self.all_packets.put(self.buffer.pop(self.expected_seq))
                            self.expected_seq += 1
                    elif seq > self.expected_seq:
                        self.buffer[seq] = payload
            elif channel == CHANNEL_UNRELIABLE:
                # deliver immediately, no ACK
                self.all_packets.put(payload)
            elif channel == CHANNEL_ACK:
                return ("ACK", seq)
        except Exception:
            pass

    def get_ordered_payloads(self):
        payloads = []
        while not self.all_packets.empty():
            payloads.append(self.all_packets.get())
        return payloads


class GameNetSocket:
    def __init__(self, local_addr, remote_addr=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)
        self.metrics = Metrics()
        self.sender = ReliableSender(self.sock, remote_addr, metrics=self.metrics) if remote_addr else None
        self.receiver = ReliableReceiver(self.sock, metrics=self.metrics)
        self.running = False
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)

    def _recv_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                result = self.receiver.handle_packet(data, addr)
                if result and isinstance(result, tuple) and result[0]=="ACK":
                    if self.sender:
                        self.sender.handle_ack(result[1])
            except Exception:
                pass

    def start(self):
        self.running = True
        self.recv_thread.start()

    def stop(self):
        self.running = False
        if self.sender:
            self.sender.stop()
        self.recv_thread.join(timeout=1.0)

    def send_reliable(self, payload: bytes):
        if self.sender:
            return self.sender.send_reliable(payload)

    def send_unreliable(self, payload: bytes):
        if self.sender:
            pkt = pack_packet(CHANNEL_UNRELIABLE, 0, now_ms(), payload)
            self.sock.sendto(pkt, self.sender.remote)
            self.metrics.add_sent(len(pkt))

    def get_ordered_payloads(self):
        return self.receiver.get_ordered_payloads()

    def get_metrics(self):
        return self.metrics.snapshot()
