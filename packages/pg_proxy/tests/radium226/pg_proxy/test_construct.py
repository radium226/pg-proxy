from construct import (
    Enum,
    Bytes,
)


def test_construct() -> None:
    server_response = Enum(Bytes(1), 
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

    print(server_response.parse(b"R"))