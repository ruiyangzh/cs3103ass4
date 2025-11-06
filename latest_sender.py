# sender.py
import time, random
from gamenet_api import GameNetSocket

REMOTE_ADDR = ("127.0.0.1", 9999)
LOCAL_ADDR = ("0.0.0.0", 0)

gnet = GameNetSocket(LOCAL_ADDR, REMOTE_ADDR)
gnet.start()

try:
    for i in range(50):
        msg = f"Packet {i}".encode()
        if random.random() < 0.7:
            seq = gnet.send_reliable(msg)
            print(f"Sent RELIABLE seq={seq} data={msg}")
        else:
            gnet.send_unreliable(msg)
            print(f"Sent UNRELIABLE data={msg}")
        time.sleep(0.02)  # 50 packets/sec
finally:
    time.sleep(1)
    gnet.stop()
    print("Metrics:", gnet.get_metrics())
