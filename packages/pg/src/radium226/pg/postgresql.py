from pathlib import Path
from subprocess import Popen, run
from contextlib import ExitStack, closing, contextmanager
from signal import SIGTERM
from temppathlib import TemporaryDirectory
import psycopg2

from .random_port import random_port
from .retry import retry


class PostgreSQL():

    _folder_path: Path
    _port: int | None
    _exit_stack: ExitStack


    def __init__(self, folder_path: Path | None = None):
        self._exit_stack = ExitStack()
        self._port = None

        if folder_path is None:
            self._folder_path = self._exit_stack.enter_context(TemporaryDirectory()).path
        else:
            self._folder_path = folder_path

    def __enter__(self):
        self._folder_path.mkdir(parents=True, exist_ok=True)
        if not ( self._folder_path / "PG_VERSION" ).exists():
            self._init_database()

        port = self._start_instance()
        self._port = port
        self._wait_for_instance()
        return self


    def _init_database(self):
        command = [
            "initdb",
            "-D", f"{self._folder_path}",
            "-U", "postgres",
        ]
        run(command, check=True)


    def _start_instance(self) -> int:
        port = random_port()
        command = [
            "postgres", 
            "-D", f"{self._folder_path}",
            "-c", f"unix_socket_directories={self._folder_path.absolute()}",
            "-c", f"port={port}",
            "-c", f"listen_addresses=localhost",
        ]

        process = Popen(command)
        def stop_process():
            process.send_signal(SIGTERM)
            process.wait()
        self._exit_stack.callback(stop_process)

        return port

    @contextmanager
    def connect(self):
        with closing(psycopg2.connect(
            dbname="postgres",
            user="postgres",
            host="localhost",
            port=self.port,
        )) as connection:
            yield connection

    @property
    def port(self) -> int:
        if port := self._port:
            return port
        
        raise Exception("Port is not yet known! ")


    @property
    def host(self) -> str:
        return "localhost"


    @retry(times=5, wait=1)
    def _wait_for_instance(self):
        command = [
            "pg_isready",
            "-h", "localhost",
            "-p", f"{self.port}",
            "-U", "postgres",
        ]
        run(command, check=True)


    def __exit__(self, type, value, traceback):
        self._exit_stack.close()
        return False