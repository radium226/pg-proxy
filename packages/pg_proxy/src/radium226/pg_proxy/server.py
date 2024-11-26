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
from typing import Protocol, Generator

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


MAX_INPUT_BYTES_LENGTH = 1024 * 1024


class Handler(Protocol):

    def handle(self, input_buffer: BytesIO, output_buffer: BytesIO) -> None:
        ...


class Server():

    _exit_stack: ExitStack
    
    _loop_thread: Thread
    _command_queue: Queue

    _host: str
    _port: int


    def __init__(self, host, port, handler: Handler):
        self._stopper = None
        self._exit_stack = ExitStack()
        self._command_queue = Queue()
        self._loop_thread = LoopThread(target=self._loop, args=(host, port,))
        self._host = host
        self._port = port
        self._handler = handler


    def _loop(self, host, port):
        selector = DefaultSelector()

        handler = self._handler

        def accept_connection(server_socket, mask):
            connection_socket, _ = server_socket.accept()
            connection_socket.setblocking(False)
            selector.register(
                connection_socket, 
                EVENT_READ | EVENT_WRITE,
                data=partial(handle_session, self, b""),
            )


        def handle_session(server, output_bytes: bytes, connection_socket, mask):
            if mask & EVENT_READ:
                print("Reading! ")
                input_bytes = b""
                while True:
                    try:
                        input_chunk = connection_socket.recv(int(MAX_INPUT_BYTES_LENGTH / 1024))
                        print(f"input_chunk={input_chunk}")
                        input_bytes += input_chunk
                        if len(input_bytes) > MAX_INPUT_BYTES_LENGTH:
                            connection_socket.shutdown(socket.SHUT_RDWR)
                            connection_socket.close()
                            selector.unregister(connection_socket)
                            return 

                    except BlockingIOError:
                        break

                if input_bytes.startswith(b"STOP"):
                    connection_socket.shutdown(socket.SHUT_RDWR)
                    connection_socket.close()
                    selector.unregister(connection_socket)
                    server.stop(wait_for=False)
                    return
                
                input_buffer = BytesIO(input_bytes)
                output_buffer = BytesIO()

                print(f"input_buffer.getvalue()={input_buffer.getvalue()}")
                handler.handle(input_buffer, output_buffer)
                print(f"output_buffer.getvalue()={output_buffer.getvalue()}")
                output_bytes += output_buffer.getvalue()
                new_mask = EVENT_WRITE

            if mask & EVENT_WRITE:

                print("Writing! ")
                n = connection_socket.send(output_bytes)
                output_bytes = output_bytes[n:]
                new_mask = EVENT_READ if len(output_bytes) == 0 else EVENT_WRITE
            
            selector.modify(connection_socket, new_mask, data=partial(handle_session, server, output_bytes))

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen()
        selector.register(
            server_socket, 
            EVENT_READ, 
            data=accept_connection,
        )

        while True:
            events = selector.select()
            try:
                command = self._command_queue.get_nowait()
            except Empty:
                command = ServerCommand.CONTINUE
            
            if command == ServerCommand.BREAK:
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
        
        
    def stop(self, wait_for=True):
        self._command_queue.put(ServerCommand.BREAK)
        try:
            self._dummy_connect()
        except ConnectionRefusedError:
            pass

        if wait_for:
            self.wait_for()