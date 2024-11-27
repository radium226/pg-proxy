import io
import struct

from radium226.socket_forwarder import EventHandler

from .server import (
    Server,
    Handler,
)

from construct import (
    Enum, 
    Bytes,
    this,
    Struct,
    Int,
    GreedyBytes,
    Switch,
    Pass,
    PaddedString,
    RawCopy,
    Transformed,
    Array,
    RepeatUntil,
    CString,
)

from io import BufferedReader, BufferedWriter, BytesIO

NULL_BYTE = b"\x00"

class ServerResponse:
    """Byte codes for server responses in the PG wire protocol."""

    AUTHENTICATION_REQUEST = b"R"
    BACKEND_KEY_DATA = b"K"
    BIND_COMPLETE = b"2"
    CLOSE_COMPLETE = b"3"
    COMMAND_COMPLETE = b"C"
    DATA_ROW = b"D"
    EMPTY_QUERY_RESPONSE = b"I"
    ERROR_RESPONSE = b"E"
    NO_DATA = b"n"
    NOTICE_RESPONSE = b"N"
    PARAMETER_DESCRIPTION = b"t"
    PARAMETER_STATUS = b"S"
    PARSE_COMPLETE = b"1"
    PORTAL_SUSPENDED = b"s"
    READY_FOR_QUERY = b"Z"
    ROW_DESCRIPTION = b"T"


class BVBuffer(object):
    """A helper for reading and writing bytes in the format the PG wire protocol expects."""

    def __init__(self, stream=None):
        if not stream:
            stream = io.BytesIO()
        self.stream = stream

    def read_bytes(self, n) -> bytes:
        return self.stream.read(n)

    def read_byte(self) -> bytes:
        return self.read_bytes(1)

    def read_int16(self) -> int:
        data = self.read_bytes(2)
        return struct.unpack("!h", data)[0]

    def read_uint32(self) -> int:
        data = self.read_bytes(4)
        return struct.unpack("!I", data)[0]

    def read_int32(self) -> int:
        data = self.read_bytes(4)
        return struct.unpack("!i", data)[0]

    def write_bytes(self, value: bytes):
        self.stream.write(value)

    def write_byte(self, value):
        self.stream.write(struct.pack("!c", value))

    def write_int16(self, value: int):
        self.stream.write(struct.pack("!h", value))

    def write_int32(self, value: int):
        self.stream.write(struct.pack("!i", value))

    def write_string(self, value):
        self.stream.write(value.encode() if isinstance(value, str) else value)
        self.stream.write(b"\x00")

    def get_value(self) -> bytes:
        return self.stream.getvalue()


# class Handler(socketserver.StreamRequestHandler):

#     def send_error(self, message: str):
#         estr = message
#         buf = BVBuffer()
#         buf.write_byte(b"M")
#         buf.write_string(estr)
#         buf.write_byte(NULL_BYTE)
#         out = buf.get_value()
#         err_sig = struct.pack("!ci", ServerResponse.ERROR_RESPONSE, len(out) + 4)
#         self.wfile.write(err_sig + out)

#     def handle(self):
#         self.send_error("Wut? ")


class WireReader():

    def __init__(self, buffered_reader: BufferedReader):
        self.buffered_reader = buffered_reader


class WireWriter():

    def __init__(self, stream: BufferedWriter | None = None):
        self.stream = stream or BytesIO()

    def write_bytes(self, value: bytes):
        self.stream.write(value)

    def write_byte(self, value):
        self.stream.write(struct.pack("!c", value))

    def write_int16(self, value: int):
        self.stream.write(struct.pack("!h", value))

    def write_int32(self, value: int):
        self.stream.write(struct.pack("!i", value))

    def write_string(self, value):
        self.stream.write(value.encode() if isinstance(value, str) else value)
        self.stream.write(b"\x00")

    def get_value(self) -> bytes:
        return self.stream.getvalue()


class WireEventHandler(EventHandler):

    def __init__(self):
        pass

    def on_data_received(self, data: bytes):
        print(f"Data received! data={data}")
        return

    def on_data_sent(self, data: bytes):
        print(f"Data sent! data={data}")
        return 
    
        buffer = BytesIO(data)

        print("Handling! ")

        client_command = Enum(
            Bytes(1),
            bind=b"B",
            close=b"C",
            describe=b"D",
            execute=b"E",
            flush=b"H",
            query=b"Q",
            parse=b"P",
            password_message=b"p",
            sync=b"S",
            terminate=b"X",
        )

        
        FirstMessageCode = Enum(
            Int, 
            ssl_request=80877103,
            startup_message=196608,
        )

        MessageLength = Int

        FirstMessage = Struct(
            "message_length" / MessageLength,
            "code" / FirstMessageCode,
        )

        SSLRequest = Pass

        Parameters = RepeatUntil(
            lambda value, list_containers, context: len(value) == 0,
            CString("utf8"),
        )

        def StartupMessage(message_length: int):
            return Struct(
                "parameters" / Parameters
            )

        ServerResponseCode = Enum(
            Bytes(1),
            authentication_request=b"R",
            backend_key_data=b"K",
            bind_complete=b"2",
            close_complete=b"3",
            command_complete=b"C",
            data_row=b"D",
            empty_query_response=b"I",
            error_response=b"E",
            no_data=b"n",
            notice_response=b"N",
            parameter_description=b"t",
            parameter_status=b"S",
            parse_complete=b"1",
            portal_suspended=b"s",
            ready_for_query=b"Z",
            row_description=b"T",
        )

        first_message = FirstMessage.parse_stream(buffer)
        print(first_message)

        match first_message.code:
            case "ssl_request":
                print("SSL request! ")
                # SSLRequest.parse_stream(buffer)
                
            case "startup_message":
                print("Startup message! ")
                # payload = Bytes(first_message.message_length - FirstMessage.sizeof()).parse_stream(buffer)
                # parameters = Parameters.parse_stream(BytesIO(payload))
                # parameters = dict(list(zip(parameters[::2], parameters[1::2])))
                # print(parameters)
                
        print("We are here! ")