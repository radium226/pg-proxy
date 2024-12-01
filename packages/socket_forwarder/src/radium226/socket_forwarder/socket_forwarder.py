from dataclasses import (
    dataclass, 
    field,
)
from contextlib import ExitStack
from functools import partial
from threading import Thread
from enum import StrEnum, auto
import selectors
import socket
from typing import Protocol
from queue import Queue, Empty
import ssl

from .host_and_port import HostAndPort


class Side(StrEnum):

    UPSTREAM = auto()
    DOWNSTREAM = auto()


class Command(StrEnum):

    BREAK_LOOP = auto()
    CONTINUE_LOOP = auto()


BUFFER_SIZE = 4096


@dataclass
class ForwardingContext():

    upstream_connection_socket: socket.socket
    downstream_connection_socket: socket.socket

    upstream_to_downstream_buffer: bytes = field(default=b"")
    downstream_to_upstream_buffer: bytes = field(default=b"")

    last_full_upstream_to_downstream_buffer: bytes = field(default=b"")
    last_full_downstream_to_upstream_buffer: bytes = field(default=b"")


class EventHandler(Protocol):

    def on_data_sent(self, context: ForwardingContext, upstream_to_downstream_buffer: bytes) -> bytes:
        ...

    def on_data_received(self, context: ForwardingContext, downstream_to_upstream_buffer: bytes) -> bytes:
        ...


class SocketForwarder():

    _local_host_and_port: HostAndPort
    _remote_host_and_port: HostAndPort

    _exit_stack: ExitStack

    _ssl_context: ssl.SSLContext | None = None

    _command_queue: Queue
    _loop_thread: Thread | None
    _event_handler: EventHandler | None

    def __init__(self, 
        local_host_and_port: HostAndPort, 
        remote_host_and_port: HostAndPort,
        event_hander: EventHandler | None = None

    ):
        self._local_host_and_port = local_host_and_port
        self._remote_host_and_port = remote_host_and_port
        self._event_handler = event_hander

        self._exit_stack = ExitStack()
        self._command_queue = Queue()


    def __enter__(self):
        selector = self._exit_stack.enter_context(selectors.DefaultSelector())

        # ssl_context_for_downstream = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # ssl_context_for_upstream = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        downstream_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        downstream_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        downstream_server_socket.bind(self._local_host_and_port.as_tuple())
        downstream_server_socket.listen()
        # downstream_server_socket = self._exit_stack.enter_context(ssl_context_for_downstream.wrap_socket(_downstream_server_socket, server_side=True))
        selector.register(
            downstream_server_socket, 
            selectors.EVENT_READ | selectors.EVENT_WRITE, 
            data=None,
        )

        def accept_connection():
            #print("[accept_connection] We're going to accept a new connection from downstream... ")
            downstream_connection_socket, _ = downstream_server_socket.accept()
            downstream_connection_socket.setblocking(False)
            #print("[accept_connection] We've accepted a new connection from downstream! ")

            #print("[accept_connection] We're going to connect to the upstream server... ")
            upstream_connection_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # upstream_connection_socket = self._exit_stack.enter_context(ssl_context_for_upstream.wrap_socket(upstream_connection_socket, server_hostname="localhost"))
            upstream_connection_socket.setblocking(False)
            upstream_connection_socket.connect_ex(self._remote_host_and_port.as_tuple())
            #print("[accept_connection] We've connected to the upstream server! ")

            context = ForwardingContext(
                upstream_connection_socket=upstream_connection_socket,
                downstream_connection_socket=downstream_connection_socket,
            )

            selector.register(
                downstream_connection_socket, 
                selectors.EVENT_READ,
                data=(Side.DOWNSTREAM, context, None, None),
            )

            selector.register(
                upstream_connection_socket, 
                selectors.EVENT_READ,
                data=(Side.UPSTREAM, context, None, None),
            )


        def handle_connection(
            side: Side, 
            context: ForwardingContext, 
            close_upstream_connection_socket_after_write: bool | None, 
            close_downstream_connection_socket_after_write: bool | None,    
            mask
        ):
            if mask & selectors.EVENT_READ:
                match side:
                    case Side.UPSTREAM:
                        #print(f"[handle_connection/selectors.EVENT_READ/Side.UPSTREAM] Reading data from upstream... ")
                        chunk = context.upstream_connection_socket.recv(BUFFER_SIZE)
                        context.upstream_to_downstream_buffer += chunk
                        close_downstream_connection_socket_after_write = len(chunk) == 0
                        if close_downstream_connection_socket_after_write:
                            #print(f"[handle_connection/selectors.EVENT_READ/Side.DOWNSTREAM] Unregistering upstream connection socket... ")
                            selector.unregister(context.upstream_connection_socket)
                        
                        #print(f"[handle_connection/selectors.EVENT_READ/Side.UPSTREAM] chunk={chunk}")
                        #print(f"[handle_connection/selectors.EVENT_READ/Side.UPSTREAM] close_downstream_connection_socket_after_write={close_downstream_connection_socket_after_write}")
                        if len(context.upstream_to_downstream_buffer) > 0 or close_downstream_connection_socket_after_write:
                            selector.modify(
                                context.downstream_connection_socket, 
                                selectors.EVENT_WRITE,
                                data=(Side.DOWNSTREAM, context, False, close_downstream_connection_socket_after_write),
                            )

                    case Side.DOWNSTREAM:
                        #print(f"[handle_connection/selectors.EVENT_READ/Side.DOWNSTREAM] Reading data from downstream... ")
                        chunk = context.downstream_connection_socket.recv(BUFFER_SIZE)
                        context.downstream_to_upstream_buffer += chunk
                        close_upstream_connection_socket_after_write = len(chunk) == 0
                        if close_upstream_connection_socket_after_write:
                            #print(f"[handle_connection/selectors.EVENT_READ/Side.DOWNSTREAM] Unregistering downstream connection socket... ")
                            selector.unregister(context.downstream_connection_socket)

                        #print(f"[handle_connection/selectors.EVENT_READ/Side.DOWNSTREAM] chunk={chunk}")
                        #print(f"[handle_connection/selectors.EVENT_READ/Side.DOWNSTREAM] close_upstream_connection_socket_after_write={close_upstream_connection_socket_after_write}")
                        if len(context.downstream_to_upstream_buffer) > 0 or close_upstream_connection_socket_after_write:
                            selector.modify(
                                context.upstream_connection_socket, 
                                selectors.EVENT_WRITE,
                                data=(Side.UPSTREAM, context, close_upstream_connection_socket_after_write, False),
                            )

            if mask & selectors.EVENT_WRITE:
                match side:
                    case Side.UPSTREAM:
                        if len(context.last_full_downstream_to_upstream_buffer) == 0:
                            context.last_full_downstream_to_upstream_buffer = context.downstream_to_upstream_buffer

                        #print(f"[handle_connection/selectors.EVENT_WRITE/Side.UPSTREAM] Sending data from downstream to upstream... ")
                        try:
                            n = context.upstream_connection_socket.send(context.downstream_to_upstream_buffer)
                            context.downstream_to_upstream_buffer = context.downstream_to_upstream_buffer[n:]
                        except BrokenPipeError:
                            selector.unregister(context.downstream_connection_socket)
                            context.downstream_connection_socket.shutdown(socket.SHUT_RDWR)
                            context.downstream_connection_socket.close()
                            return

                        if len(context.downstream_to_upstream_buffer) == 0:
                            if event_handler := self._event_handler:
                                    event_handler.on_data_sent(context)

                            if close_upstream_connection_socket_after_write:
                                selector.unregister(context.upstream_connection_socket)
                                context.upstream_connection_socket.shutdown(socket.SHUT_RDWR)
                                context.upstream_connection_socket.close()
                            else:
                                selector.modify(
                                    context.upstream_connection_socket, 
                                    selectors.EVENT_READ,
                                    data=(Side.UPSTREAM, context, None, None),
                                )

                    case Side.DOWNSTREAM:
                        #print(f"[handle_connection/selectors.EVENT_WRITE/Side.DOWNSTREAM] Sending data from upstream to downstream... ")
                        try:
                            n = context.downstream_connection_socket.send(context.upstream_to_downstream_buffer)
                            context.upstream_to_downstream_buffer = context.upstream_to_downstream_buffer[n:]
                        except BrokenPipeError:
                            selector.unregister(context.upstream_connection_socket)
                            context.upstream_connection_socket.shutdown(socket.SHUT_RDWR)
                            context.upstream_connection_socket.close()
                            return
                        
                        if len(context.upstream_to_downstream_buffer) == 0:
                            if event_handler := self._event_handler:
                                event_handler.on_data_received(context)
                                
                            if close_downstream_connection_socket_after_write:
                                selector.unregister(context.downstream_connection_socket)
                                context.downstream_connection_socket.shutdown(socket.SHUT_RDWR)
                                context.downstream_connection_socket.close()
                            else:
                                selector.modify(
                                    context.downstream_connection_socket, 
                                    selectors.EVENT_READ,
                                    data=(Side.DOWNSTREAM, context, None, None),
                                )

        def loop(command_queue: Queue):
            while True:
                events = selector.select()
                try:
                    command = command_queue.get_nowait()
                except Empty:
                    command = Command.CONTINUE_LOOP

                #print(f"[loop] command={command}")

                if command == Command.BREAK_LOOP:
                    break

                for key, mask in events:
                    if downstream_server_socket.fileno() == key.fileobj.fileno():
                        accept_connection()
                    else:
                        side, context, close_upstream_connection_socket_after_write, close_downstream_connection_socket_after_write = key.data
                        handle_connection(
                            side, 
                            context, 
                            close_upstream_connection_socket_after_write, 
                            close_downstream_connection_socket_after_write, 
                            mask,
                        )

        self._command_queue = Queue()

        self._loop_thread = Thread(target=loop, args=(self._command_queue,))

        self._loop_thread.start()
        self._exit_stack.callback(self._loop_thread.join)

        return self
    

    def _dummy_connect(self):
        dummy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dummy_socket.connect(self._local_host_and_port.as_tuple())
        dummy_socket.shutdown(socket.SHUT_RDWR)
        dummy_socket.close()

    def stop(self, wait_for=True):
        self._command_queue.put(Command.BREAK_LOOP)
        try:
            self._dummy_connect()
        except Exception:
            pass
        if wait_for:
            self.wait_for()


    def __exit__(self, type, value, traceback):
        self.stop(wait_for=False)
        self._exit_stack.close()

    def wait_for(self):
        self._loop_thread.join()