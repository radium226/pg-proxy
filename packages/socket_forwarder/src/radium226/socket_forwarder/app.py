from click import command, argument

from .socket_forwarder import SocketForwarder, EventHandler
from .host_and_port import HostAndPort

from time import sleep


class PrintEventHandler(EventHandler):

    def on_data_received(self, buffer: bytes):
        print(f"We received some data! buffer={buffer}")

    def on_data_sent(self, buffer: bytes):
        print(f"We sent some data! buffer={buffer}")



@command
@argument("local_address")
@argument("remote_address")
def app(local_address: str, remote_address: str):
    local_host_and_port = HostAndPort.parse_address(local_address)
    print(f"local_host_and_port: {local_host_and_port}")

    remote_host_and_port = HostAndPort.parse_address(remote_address)
    print(f"remote_host_and_port: {remote_host_and_port}")
    
    with SocketForwarder(
        local_host_and_port=local_host_and_port,
        remote_host_and_port=remote_host_and_port,
        event_hander=PrintEventHandler(),

    ) as socket_forwarder:
        print("We are here! ")
        sleep(5)

        print("We still here! ")
        socket_forwarder.stop()
        print("We finally here! ")
        # socket_forwarder.wait_for()