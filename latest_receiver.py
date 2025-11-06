# receiver.py
import time
from gamenet_api import GameNetSocket

LOCAL_ADDR = ("0.0.0.0", 9999)

gnet = GameNetSocket(LOCAL_ADDR)
gnet.start()
print("Receiver started...")

try:
    while True:
        payloads = gnet.get_ordered_payloads()
        for p in payloads:
            print(f"Received: {p}")
        time.sleep(0.01)
finally:
    gnet.stop()
    print("Metrics:", gnet.get_metrics())
