import sys
import os
import time
import threading

# Add workspace to path
sys.path.append(r"c:\Users\Harsh\Downloads\files(2)")

from udp_core import ReliableUDPNode

def test_dynamic_registration():
    received_msgs = []

    def on_msg_server(sender, msg, addr):
        print(f"[SERVER RECV] {sender}: {msg} from {addr}")
        received_msgs.append(msg)

    def on_msg_client(sender, msg, addr):
        print(f"[CLIENT RECV] {sender}: {msg} from {addr}")
        received_msgs.append(msg)

    def on_ack(addr, seq, ok):
        pass

    # Start Server on 9999
    server = ReliableUDPNode("ServerNode", on_msg_server, on_ack)
    server.start_server(9999, []) # Empty peer list

    # Start Client on 9998
    client = ReliableUDPNode("ClientNode", on_msg_client, on_ack)
    client.start_client(9998, ("127.0.0.1", 9999))

    time.sleep(1)

    # Client sends to Server
    print("Client sending message...")
    client.send_notification("Hello Server")

    time.sleep(1)

    # Server should now have client in its list and can reply
    print("Server sending broadcast reply...")
    server.send_notification("Hello Client")

    time.sleep(1)

    server.stop()
    client.stop()

    if "Hello Server" in received_msgs and "Hello Client" in received_msgs:
        print("TEST PASSED!")
    else:
        print(f"TEST FAILED! Msgs: {received_msgs}")

if __name__ == "__main__":
    test_dynamic_registration()
