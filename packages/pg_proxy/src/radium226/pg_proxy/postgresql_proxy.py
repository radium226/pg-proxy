import socket
import socketserver
from contextlib import ExitStack
from threading import Thread
from io import BytesIO

from .wire import (
    WireHandler,
    WireWriter,
    WireReader
)    

from .forwarder import server

class PostgreSQLProxy():

    _host: str
    _port: int

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
    


    def __enter__(self):
        socket_server = server(
            self._local_host,
            self._local_port,
            self._remote_host,
            self._remote_port,
        )

        def stop_server():
            socket_server.shutdown(socket.SHUT_RDWR)
            socket_server.close()

        self._exit_stack.callback(stop_server)

        return self


    def BACKUP__enter__(self):        
        print("Creating proxy server! ")

        wire_handler = WireHandler()

        class Handler(socketserver.StreamRequestHandler):

            def handle(self) -> None:
                while True:
                    if not wire_handler.handle(
                        self.rfile, 
                        self.wfile,
                    ):
                        break

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True

            # def server_bind(self):
            #     self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            #     self.socket.bind(self.server_address)

        server = Server(
            (self._host, self._port), 
            Handler
        )

        def start_server():
            print("Serving forever! ")
            server.serve_forever()
            print("Done serving forever! ")

        def stop_server():
            print("Stopping server! ")
            server.shutdown()
            print("Server stopped! ")

        def join_server_thread():
            print("Waiting for server thread! ")
            server_thread.join()
            print("Server thread done! ")

        self._exit_stack.callback(join_server_thread)
        self._exit_stack.callback(stop_server)
        
        server_thread = Thread(target=start_server)
        server_thread.start()

        return self


    @property
    def port(self) -> int:
        return self._local_port


    @property
    def host(self) -> str:
        return self._local_host


    def __exit__(self, type, value, traceback):
        print("Proxy server stopped! ")
        self._exit_stack.close()
        print("Proxy server stopped2! ")
        return False


    def wait_forever(self) -> None:
        if server := self._server:
            server.serve_forever()
        
        raise ValueError("The server is not running")