import gameNetAPI
import time 
client = ('127.0.0.1', 20000)
server = ('127.0.0.1', 20001)
bufferSize  = 1024

api = gameNetAPI.gameNetAPI(server, client)
while True:
    seqno, channel_type, timestamp_ms, retransmissions, packet_arrivals = api.recieve_packet()
    print(f'''Received message from {client}. 
        seqno:{seqno} 
        channel_type:{channel_type} 
        timestamp:{timestamp_ms}
        retransmissions:{retransmissions}
        packet arrivals:{packet_arrivals}
        rtt:{2 * ((time.time()*1000) - timestamp_ms)} ms
''')
