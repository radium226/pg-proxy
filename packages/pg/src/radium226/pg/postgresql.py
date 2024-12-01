from pathlib import Path
from subprocess import Popen, run
from contextlib import ExitStack, closing, contextmanager
from signal import SIGTERM
from temppathlib import TemporaryDirectory
import psycopg2
from os import chmod
from shutil import copy2 as copy
from textwrap import dedent

from .random_port import random_port
from .retry import retry


class PostgreSQL():

    _folder_path: Path
    _port: int | None
    _exit_stack: ExitStack


    def __init__(self, ssl: bool = False, folder_path: Path | None = None):
        self._exit_stack = ExitStack()
        self._port = None
        self._ssl = ssl

        if folder_path is None:
            self._folder_path = self._exit_stack.enter_context(TemporaryDirectory()).path
        else:
            self._folder_path = folder_path

    def __enter__(self):
        self._folder_path.mkdir(parents=True, exist_ok=True)
        if not ( self._folder_path / "PG_VERSION" ).exists():
            self._init_database()
            if self._ssl:
                self._generate_ssl_certificates()

        port = self._start_instance()
        self._port = port
        self._wait_for_instance()
        return self


    def _generate_ssl_certificates(self):
        command = [
            "openssl",
            "req",
            "-nodes",
            "-new",
            "-x509",
            "-keyout", f"{self._folder_path}/server.key",
            "-out", f"{self._folder_path}/server.crt",
            "-subj", "/C=US/ST=Test/L=Test/O=Test/CN=localhost",
        ]
        run(command, check=True)

        chmod(f"{self._folder_path}/server.key", 0o400)
        copy(f"{self._folder_path}/server.crt", f"{self._folder_path}/root.crt")

        with ( self._folder_path / "postgresql.conf" ).open("a") as file:
            file.write(dedent("""\
                ssl = on
                ssl_ca_file = 'root.crt'
                ssl_cert_file = 'server.crt'
                ssl_crl_file = ''
                ssl_key_file = 'server.key'
                ssl_ciphers = 'HIGH:MEDIUM:+3DES:!aNULL' # allowed SSL ciphers
                ssl_prefer_server_ciphers = on
            """))
        

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
            sslmode="require" if self._ssl else "disable",
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
    
    @property
    def folder_path(self) -> Path:
        return self._folder_path