import socket
import threading
import queue
import time

class UdpTransport: 
    def __init__(self, server_addr, bind_addr, on_recv):
        self.server_addr = server_addr
        self.on_recv = on_recv
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(bind_addr)
        self._stop = False

        self._t = threading.Thread(target=self._rx_loop, daemon=True)
        self._t.start()

    def _rx_loop(self):
        self.sock.settimeout(0.2)
        while not self._stop:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            # feed incoming datagrams into your API
            self.on_recv(data, addr)

    def send(self, data: bytes):
        self.sock.sendto(data, self.server_addr)

    def close(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass