from contextlib import ExitStack
from threading import Thread
from queue import Queue, Empty
from enum import StrEnum, auto
from functools import partial
import socket
from selectors import (
    DefaultSelector,
    EVENT_READ,
    EVENT_WRITE,
)

from io import BytesIO


from time import sleep



class ServerCommand(StrEnum):

    BREAK = auto()
    CONTINUE = auto()


class LoopThread(Thread):

    _exception: Exception | None

    def __init__(self, 
        group=None, 
        target=None, 
        name=None,
        args=(), 
        kwargs=None, 
        *, 
        daemon=None,
    ):
        super().__init__(
            group,
            target,
            name,
            args,
            kwargs,
            daemon=daemon,
        )

        self._exception = None

    def join(self):
        super().join()
        if self._exception is not None:
            raise self._exception



class Server():

    _exit_stack: ExitStack
    
    _loop_thread: Thread
    _command_queue: Queue

    _host: str
    _port: int


    def __init__(self, host, port):
        self._stopper = None
        self._exit_stack = ExitStack()
        self._command_queue = Queue()
        self._loop_thread = LoopThread(target=self._loop, args=(host, port,))
        self._host = host
        self._port = port


    def _loop(self, host, port):
        selector = DefaultSelector()

        def accept_connection(server_socket, mask):
            print("We are here! ")
            connection_socket, _ = server_socket.accept()
            connection_socket.setblocking(False)
            selector.register(
                connection_socket, 
                EVENT_READ | EVENT_WRITE,
                data=partial(handle_session, b""),
            )


        def handle_session(output_bytes: bytes, connection_socket, mask):
            print(f"We are also here! mask={mask}")
            if mask & EVENT_READ:
                print("Here! ")
                input_bytes = b""
                while True:
                    try:
                        chunk = connection_socket.recv(4096)
                        print(f"chunk={chunk}")
                        input_bytes += chunk
                    except BlockingIOError:
                        break
                
                output_bytes += input_bytes.decode("utf-8").upper().encode("utf-8")
                mask = EVENT_WRITE

            if mask & EVENT_WRITE:
                print("No ! Here! ")
                    
                if len(output_bytes) == 0:
                    mask = EVENT_READ
                else:
                    n = connection_socket.send(output_bytes)
                    output_bytes = output_bytes[n:]
                    if (len(output_bytes) == 0):
                        mask = EVENT_READ
            
            selector.modify(connection_socket, mask, data=partial(handle_session, output_bytes))

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen()
        selector.register(
            server_socket, 
            EVENT_READ, 
            data=accept_connection,
        )

        while events := selector.select():
            try:
                command = self._command_queue.get_nowait()
            except Empty:
                command = ServerCommand.CONTINUE
            
            if command == ServerCommand.BREAK:
                print("Stopping the server! ")
                break

            for key, mask in events:
                callback = key.data
                callback(key.fileobj, mask)

        selector.unregister(server_socket)
        server_socket.shutdown(socket.SHUT_RDWR)
        server_socket.close()


    def wait_for(self):
        self._loop_thread.join()


    def __enter__(self):
        self._loop_thread.start()
        self._exit_stack.callback(self.stop)
        return self
    

    def __exit__(self, type, value, traceback):
        self._exit_stack.close()

    def _dummy_connect(self):
        dummy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dummy_socket.connect((self._host, self._port))
        dummy_socket.shutdown(socket.SHUT_RDWR)
        dummy_socket.close()
        
        
    def stop(self):
        self._command_queue.put(ServerCommand.BREAK)
        try:
            self._dummy_connect()
        except ConnectionRefusedError:
            pass

        self.wait_for()