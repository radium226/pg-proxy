from contextlib import ExitStack
import socket
import select
import os
from threading import Thread
from time import sleep

import selectors


class SocketForwarder():

    _exit_stack: ExitStack


    def __init__(self):
        self._exit_stack = ExitStack()
        

    def __enter__(self):

        server_socket = self._exit_stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('localhost', 7654))
        server_socket.listen()

        stop_accept_loop_read_file_no, stop_accept_loop_write_file_no = os.pipe()
        self._exit_stack.callback(os.close, stop_accept_loop_read_file_no)
        self._exit_stack.callback(os.close, stop_accept_loop_write_file_no)

        stop_handle_loop_read_file_no, stop_handle_loop_write_file_no = os.pipe()
        self._exit_stack.callback(os.close, stop_handle_loop_read_file_no)
        self._exit_stack.callback(os.close, stop_handle_loop_write_file_no)

        selector = selectors.DefaultSelector()

        selector.register(stop_handle_loop_read_file_no, selectors.EVENT_READ, data="STOP")

        def start_accept_loop():
            while True:
                file_nos_to_read, _, _ = select.select([server_socket.fileno(), stop_accept_loop_read_file_no], [], [])
                if stop_accept_loop_read_file_no in file_nos_to_read:
                    print("Time to stop the accept loop! Goodbye!")
                    break

                connection_socket, _ = server_socket.accept()
                connection_socket.setblocking(False)
                selector.register(connection_socket, selectors.EVENT_READ | selectors.EVENT_WRITE)


        def stop_accept_loop():
            os.write(stop_accept_loop_write_file_no, b"STOP")


        def start_handle_loop():
            loop_again = True
            buffer = []
            while loop_again:
                for key, events in selector.select():
                    if key.data == "STOP":
                        print("Time to stop the handle loop! Goodbye!")
                        loop_again = False
                        break
                    
                    if events & selectors.EVENT_READ:
                        while True:
                            try:
                                data = key.fileobj.recv(2000000)
                                buffer.extend(data)
                            except BlockingIOError as e:
                                break
                        
                        if bytes(data).decode("utf-8").strip() == "QUIT":
                            selector.unregister(key.fileobj)
                            key.fileobj.shutdown(socket.SHUT_RDWR)
                            key.fileobj.close()

                    elif events & selectors.EVENT_WRITE:
                        sent = key.fileobj.send(bytes(buffer))
                        buffer = buffer[sent:]


        def stop_handle_loop():
            os.write(stop_handle_loop_write_file_no, b"STOP")

        accept_loop_thread = Thread(target=start_accept_loop)
        accept_loop_thread.start()
        self._exit_stack.callback(accept_loop_thread.join)
        self._exit_stack.callback(stop_accept_loop)

        handle_loop_thread = Thread(target=start_handle_loop)
        handle_loop_thread.start()
        self._exit_stack.callback(handle_loop_thread.join)
        self._exit_stack.callback(stop_handle_loop)

        return self


    def __exit__(self, type, value, traceback):
        self._exit_stack.close()

    def run_forever(self):
        sleep(1000)


def app():
    with SocketForwarder() as socket_forwarder:
        socket_forwarder.run_forever()