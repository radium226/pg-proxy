import socket
import socketserver
from contextlib import ExitStack
from threading import Thread
from io import BytesIO

from radium226.socket_forwarder import SocketForwarder, HostAndPort


from .server import Server
from .wire import WireEventHandler

class PostgreSQLProxy():

    _remote_host: str
    _remote_port: int

    _local_host: str
    _local_port: int

    _socket_forwarder: SocketForwarder | None = None

    def __init__(self, 
        remote_host: str, 
        remote_port: int, 
        local_host: str | None = None, 
        local_port: int | None = None
    ):
        self._remote_host = remote_host
        self._remote_port = remote_port

        self._local_host = local_host or "localhost"
        self._local_port = local_port or 5432
        
        self._exit_stack = ExitStack()


    @property
    def host(self) -> str:
        return self._local_host
    
    
    @property
    def port(self) -> int:
        return self._local_port
    

    def wait_for(self) -> None:
        if server := self._server:
            server.wait_for()
        else:
            raise ValueError("The server is not running")
    

    def __enter__(self):
        self._socket_forwarder = self._exit_stack.enter_context(
            SocketForwarder(
                HostAndPort(self._local_host, self._local_port), 
                HostAndPort(self._remote_host, self._remote_port),
                WireEventHandler()
            )
        )
        return self


    def __exit__(self, type, value, traceback):
        print("Proxy server stopped! ")
        self._exit_stack.close()
        print("Proxy server stopped2! ")
        return False