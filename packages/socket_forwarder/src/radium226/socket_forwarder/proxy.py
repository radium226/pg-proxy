from typing import (
    Protocol,
    Literal,
    TypeAlias,
    assert_never,
    cast,
    Callable,
    Generator,
)
from enum import Enum, auto
from dataclasses import dataclass, replace
from contextlib import ExitStack
from queue import Queue
import selectors
import socket
from threading import Thread

from .host_and_port import HostAndPort


@dataclass
class Buffers():
    
    upstream_to_downstream: bytes = b""
    downstream_to_upstream: bytes = b""

class Context():
    
    upstream_connection_socket: socket.socket
    downstream_connection_socket: socket.socket
    buffers: Buffers

    def __init__(self, upstream_connection_socket: socket.socket, downstream_connection_socket: socket.socket):
        self.upstream_connection_socket = upstream_connection_socket
        self.downstream_connection_socket = downstream_connection_socket
        self._exit_stack = ExitStack()
        self.buffers = Buffers()


SessionKey: TypeAlias = int


@dataclass
class Session():
    
    upstream_connection_socket: socket.socket
    upstream_connection_already_closed: bool
    data_to_write_to_upstream: bytes
    
    downstream_connection_socket: socket.socket
    downstream_connection_already_closed: bool
    data_to_write_to_downstream: bytes
    
    
    def __repr__(self):
        return f"Session(upstream_connection_already_closed={self.upstream_connection_already_closed}, downstream_connection_already_closed={self.downstream_connection_already_closed})"


class Side(Enum):

    UPSTREAM = auto()
    DOWNSTREAM = auto()


@dataclass
class CopyDataAsIs():
    pass


@dataclass
class AlterData():

    data: bytes


@dataclass
class AlterSession():
    
    session: Session

@dataclass
class WriteDataToUpstream():
    
    data: bytes


@dataclass
class WriteDataToDownstream():

    data: bytes


Action = AlterData | CopyDataAsIs | AlterSession | WriteDataToUpstream | WriteDataToDownstream


class Handler(Protocol):

    def handle_upstream_data(self, session: Session, data: bytes) -> list[Action]:
        ...

    def handle_downstream_data(self, session: Session, data: bytes) -> list[Action]:
        ...

    @staticmethod
    def copy_data_as_is() -> "Handler":
        class Impl(Handler):

            def handle_upstream_data(self, session: Session, data: bytes) -> Action:
                return [
                    CopyDataAsIs()
                ]

            def handle_downstream_data(self, session: Session, data: bytes) -> Action:
                return [
                    CopyDataAsIs(),
                ]
            
        return Impl()
    
    @staticmethod
    def alter_downstream_data(alteration: Callable[[bytes], bytes]) -> "Handler":
        class Impl(Handler):

            def handle_upstream_data(self, session: Session, data: bytes) -> list[Action]:
                return [
                    CopyDataAsIs(),
                ]

            def handle_downstream_data(self, session: Session, data: bytes) -> list[Action]:
                return [
                    AlterData(data=alteration(data)),
                ]
            
        return Impl()


class LoopCommand(Enum):

    CONTINUE = auto()
    BREAK = auto()


@dataclass
class NewConnectionToDownstream():
    pass


@dataclass
class DataToReadFromUpstream():
    
    session_key: SessionKey

@dataclass
class DataToReadFromDownstream():
    
    session_key: Session


@dataclass
class DataToWriteToUpstream():
    
    session_key: SessionKey

    def __repr__(self):
        return f"DataToWriteToUpstream(session_key={self.session_key}, data=...)"


@dataclass
class DataToWriteToDownstream():

    session_key: SessionKey

    def __repr__(self):
        return f"DataToWriteToDownstream(session_key={self.session_key}, data=...)"


@dataclass
class CloseDownstream():
    
    session_key: SessionKey


@dataclass
class CloseUpstream():

    session_key: SessionKey


IterationType = NewConnectionToDownstream | DataToReadFromUpstream | DataToWriteToUpstream | DataToReadFromDownstream | DataToWriteToDownstream | CloseDownstream | CloseUpstream


BUFFER_SIZE = 1024

next_session_key = 0

class Proxy():

    _upstream_host_and_port: HostAndPort
    _downstream_host_and_port: HostAndPort
    _handler: Handler

    _exit_stack: ExitStack
    _loop_command_queue: Queue[LoopCommand]
    _loop_thread: Thread

    _loop_thread_exception: Exception | None = None

    def __init__(self, 
        upstream_host_and_port: HostAndPort,
        downstream_host_and_port: HostAndPort,             
        handler: Handler | None = None,
    ):
        self._upstream_host_and_port = upstream_host_and_port
        self._downstream_host_and_port = downstream_host_and_port
        self._handler = handler or Handler.copy_data_as_is()

        self._exit_stack = ExitStack()
        self._loop_command_queue = Queue()
        self._loop_thread = Thread(target=self._loop_thread_target)

    @property
    def handler(self):
        return self._handler

    def __enter__(self):
        self._loop_thread.start()
        self._exit_stack.callback(self._loop_thread.join)

        return self
    
    def __exit__(self, type, value, traceback):
        self.stop(wait_for=True)
        self._exit_stack.close()
        return False

    def _dequeue_loop_command(self) -> LoopCommand:
        try:
            return self._loop_command_queue.get_nowait()
        except Exception as _:
            return LoopCommand.CONTINUE

    def _loop_thread_target(self):
        selector = selectors.DefaultSelector()

        downstream_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        downstream_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        downstream_server_socket.bind(self._downstream_host_and_port.as_tuple())
        downstream_server_socket.listen()
        
        selector.register(
            downstream_server_socket, 
            selectors.EVENT_READ | selectors.EVENT_WRITE, 
            data=NewConnectionToDownstream(),
        )

        sessions_by_key: dict[SessionKey, Session] = {}

        def modify_selector(connection_socket: socket.socket, mask: int, data: IterationType):
            if sessions_by_key[data.session_key].upstream_connection_socket.fileno() == connection_socket.fileno():
                side = "upstream_connection_socket"
            elif sessions_by_key[data.session_key].downstream_connection_socket.fileno() == connection_socket.fileno():
                side = "downstream_connection_socket"

            if mask & selectors.EVENT_READ:
                mask_str = "selectors.EVENT_READ"
            elif mask & selectors.EVENT_WRITE:
                mask_str = "selectors.EVENT_WRITE"

            print(f"selector.modify({side}, {mask_str}, data=...)")
            selector.modify(
                connection_socket,
                mask,
                data=data,
            )

        def register_selector(connection_socket: socket.socket, mask: int, data: IterationType):
            if sessions_by_key[data.session_key].upstream_connection_socket.fileno() == connection_socket.fileno():
                side = "upstream_connection_socket"
            elif sessions_by_key[data.session_key].downstream_connection_socket.fileno() == connection_socket.fileno():
                side = "downstream_connection_socket"

            if mask & selectors.EVENT_READ:
                mask_str = "selectors.EVENT_READ"
            elif mask & selectors.EVENT_WRITE:
                mask_str = "selectors.EVENT_WRITE"

            print(f"selector.register({side}, {mask_str}, data=...)")
            selector.register(
                connection_socket,
                mask,
                data=data,
            )

        def _iterate_loop(iteration_type: IterationType):
            print(iteration_type)
            match iteration_type:
                case NewConnectionToDownstream(
                ):
                    downstream_connection_socket, _ = downstream_server_socket.accept()
                    downstream_connection_socket.setblocking(False)

                    upstream_connection_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    upstream_connection_socket.setblocking(False)
                    upstream_connection_socket.connect_ex(self._upstream_host_and_port.as_tuple())
                    
                    session = Session(
                        upstream_connection_socket,
                        False,
                        b"",
                        downstream_connection_socket,
                        False,
                        b"",
                    )

                    global next_session_key
        
                    session_key = next_session_key
                    next_session_key += 1

                    sessions_by_key[session_key] = session
                    
                    register_selector(
                        upstream_connection_socket, 
                        selectors.EVENT_READ,
                        data=DataToReadFromUpstream(
                            session_key,
                        ),
                    )

                    register_selector(
                        downstream_connection_socket, 
                        selectors.EVENT_READ,
                        data=DataToReadFromDownstream(
                            session_key,
                        ),
                    )

                case DataToReadFromUpstream(
                    session_key,
                ):
                    session = sessions_by_key[session_key]

                    data = session.upstream_connection_socket.recv(BUFFER_SIZE)
                    if len(data) == 0:
                        print("No data received from upstream: closing connection")
                        selector.unregister(session.upstream_connection_socket)
                        session.upstream_connection_socket.shutdown(socket.SHUT_RDWR)
                        session.upstream_connection_socket.close()
                        sessions_by_key[session_key] = replace(session, upstream_connection_already_closed=True)
                        new_data = data

                    else:
                        for action in self._handler.handle_upstream_data(session, data):
                            print(f"Data received from upstream: len(data)={len(data)}")
                            match action:
                                case AlterData(data=new_data):
                                    pass

                                case CopyDataAsIs():
                                    print("Copying data as is")
                                    new_data = data

                                case AlterSession(session=new_session):
                                    session = new_session
                                    sessions_by_key[session_key] = session
                                
                                case WriteDataToUpstream(data=new_data):
                                    session.data_to_write_to_upstream += new_data
                                    modify_selector(
                                        session.upstream_connection_socket, 
                                        selectors.EVENT_WRITE,
                                        data=DataToWriteToUpstream(
                                            session_key,
                                        ),
                                    )

                                case WriteDataToDownstream(data=new_data):
                                    session.data_to_write_to_downstream += new_data
                                    modify_selector(
                                        session.downstream_connection_socket, 
                                        selectors.EVENT_WRITE,
                                        data=DataToWriteToDownstream(
                                            session_key,
                                        ),
                                    )

                                case _ as never:
                                    assert_never(never)

                        session.data_to_write_to_downstream += new_data

                    modify_selector(
                        session.downstream_connection_socket, 
                        selectors.EVENT_WRITE,
                        data=DataToWriteToDownstream(
                            session_key,
                        ),
                    )

                case DataToWriteToDownstream(
                    session_key,
                ):
                    session = sessions_by_key[session_key]
                    data = session.data_to_write_to_downstream
                    print(f"data={data}")

                    if len(data) == 0:
                        print("Closing downstream connection")
                        selector.unregister(session.downstream_connection_socket)
                        session.downstream_connection_socket.shutdown(socket.SHUT_RDWR)
                        session.downstream_connection_socket.close()
                        sessions_by_key[session_key] = replace(session, downstream_connection_already_closed=True)
                    else:
                        print(f"Writing data to downstream: len(data)={len(data)}")
                        number_of_written_bytes = session.downstream_connection_socket.send(data)
                        new_data = data[number_of_written_bytes:]
                        session.data_to_write_to_downstream = new_data
                        print(f"number_of_written_bytes={number_of_written_bytes}, len(new_data)={len(new_data)}")
                        if len(session.data_to_write_to_downstream) == 0:
                            if session.upstream_connection_already_closed:
                                print("Closing downstream connection (because upstream connection is already closed dans we wrote everything already)")
                                selector.unregister(session.downstream_connection_socket)
                                session.downstream_connection_socket.shutdown(socket.SHUT_RDWR)
                                session.downstream_connection_socket.close()
                                sessions_by_key[session_key] = replace(session, downstream_connection_already_closed=True)
                            else:
                                print("Switching to read mode for downstream connection")
                                modify_selector(
                                    session.downstream_connection_socket, 
                                    selectors.EVENT_READ,
                                    data=DataToReadFromDownstream(
                                        session_key,
                                    ),
                                )
                        else:
                            print("Switching to write mode for downstream connection (we have more stuff to read)")
                            modify_selector(
                                session.downstream_connection_socket, 
                                selectors.EVENT_WRITE,
                                data=DataToWriteToDownstream(
                                    session_key,
                                ),
                            )

                case DataToReadFromDownstream(
                    session_key,
                ):
                    session = sessions_by_key[session_key]

                    data = session.downstream_connection_socket.recv(BUFFER_SIZE)
                    if len(data) == 0:
                        print("No data received from downstream: closing connection")
                        selector.unregister(session.downstream_connection_socket)
                        session.downstream_connection_socket.shutdown(socket.SHUT_RDWR)
                        session.downstream_connection_socket.close()
                        sessions_by_key[session_key] = replace(session, downstream_connection_already_closed=True)
                    else:
                        modify_selector_for_upstream = True
                        for action in self._handler.handle_downstream_data(session, data):
                            match action:
                                case AlterData(data=new_data):
                                    pass

                                case CopyDataAsIs():
                                    new_data = data

                                case AlterSession(session=new_session):
                                    session = new_session
                                    sessions_by_key[session_key] = session

                                case WriteDataToUpstream(data=new_data):
                                    session.data_to_write_to_upstream += new_data
                                    modify_selector(
                                        session.upstream_connection_socket, 
                                        selectors.EVENT_WRITE,
                                        data=DataToWriteToUpstream(
                                            session_key,
                                        ),
                                    )

                                case WriteDataToDownstream(data=new_data):
                                    print("We are here! ")
                                    session.data_to_write_to_downstream += new_data
                                    session.data_to_write_to_upstream = b""
                                    modify_selector(
                                        session.downstream_connection_socket, 
                                        selectors.EVENT_WRITE,
                                        data=DataToWriteToDownstream(
                                            session_key,
                                        ),
                                    )
                                    modify_selector_for_upstream = False

                                case _ as never:
                                    assert_never(never)

                        session.data_to_write_to_upstream += new_data

                    if modify_selector_for_upstream:
                        modify_selector(
                            session.upstream_connection_socket, 
                            selectors.EVENT_WRITE,
                            data=DataToWriteToUpstream(
                                session_key, 
                            ),
                        )

                case DataToWriteToUpstream(
                    session_key,
                ):
                    session = sessions_by_key[session_key]
                    data = session.data_to_write_to_upstream
                    print(f"data={data}")
                    if len(data) == 0:
                        print("Closing upstream connection")
                        selector.unregister(session.upstream_connection_socket)
                        session.upstream_connection_socket.shutdown(socket.SHUT_RDWR)
                        session.upstream_connection_socket.close()
                        sessions_by_key[session_key] = replace(session, upstream_connection_already_closed=True)
                    else:
                        number_of_written_bytes = session.upstream_connection_socket.send(data)
                        new_data = data[number_of_written_bytes:]
                        print(f"new_data={new_data}")
                        session.data_to_write_to_upstream = new_data
                        if len(new_data) == 0:
                            if session.downstream_connection_already_closed:
                                print("Closing upstream connection (because downstream connection is already closed and we wrote everything already)")
                                selector.unregister(session.upstream_connection_socket)
                                session.upstream_connection_socket.shutdown(socket.SHUT_RDWR)
                                session.upstream_connection_socket.close()
                                sessions_by_key[session_key] = replace(session, upstream_connection_already_closed=True)
                            else:
                                modify_selector(
                                    session.upstream_connection_socket, 
                                    selectors.EVENT_READ,
                                    data=DataToReadFromUpstream(
                                        session_key,
                                    ),
                                )
                        else:
                            modify_selector(
                                session.upstream_connection_socket, 
                                selectors.EVENT_WRITE,
                                data=DataToWriteToUpstream(
                                    session_key,
                                ),
                            )
                
                case _ as never:
                    assert_never(never)

            print()


        while True:
            events = selector.select()
            loop_command = self._dequeue_loop_command()
            match loop_command:
                case LoopCommand.CONTINUE:
                    pass
                case LoopCommand.BREAK:
                    print("Breaking loop")
                    break
            
            for key, mask in events:
                iteration_type = cast(IterationType, key.data)
                _iterate_loop(iteration_type)

        print("Loop ended")
        print("Closing downstream server socket")
        selector.unregister(downstream_server_socket)
        downstream_server_socket.shutdown(socket.SHUT_RDWR)

        print("Closing selector")
        selector.close()

            

    def stop(self, wait_for: bool = True):
        self._loop_command_queue.put(LoopCommand.BREAK)
        self._dummy_connect()
        if wait_for:
            self.wait_for()

    def _dummy_connect(self):
        try:
            dummy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            dummy_socket.connect(self._downstream_host_and_port.as_tuple())
            dummy_socket.shutdown(socket.SHUT_RDWR)
            dummy_socket.close()
        except Exception as _:
            pass

    def wait_for(self):
        self._loop_thread.join()
        if self._loop_thread_exception:
            raise self._loop_thread_exception


