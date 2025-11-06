import gameNetAPI
import random, time

msgFromClient = "Hello UDP Server"
client = ('127.0.0.1', 20000)
server = ('127.0.0.1', 20001)

while True:
    # tag outgoing data packets as reliable or unreliable randomly
    if random.random() < 0.5:
        isreliable = True
    else:
        isreliable = False

    bytesToSend = str.encode(msgFromClient)
    api = gameNetAPI.gameNetAPI(client, server)
    api.send_packet(msgFromClient, isreliable)
    time.sleep(0.2)
