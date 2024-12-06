import pytest

from subprocess import (
    Popen,
    run,
    PIPE,
)

from radium226.socket_forwarder import (
    Proxy,
    HostAndPort,
    Handler,
)

HELLO_WORLD = "Hello, World!"


@pytest.mark.parametrize(
    "handler, input, expected_output",
    [
        (Handler.copy_data_as_is(), HELLO_WORLD, HELLO_WORLD),
        (Handler.alter_downstream_data(lambda data: data.upper()), HELLO_WORLD, HELLO_WORLD.upper()),
    ]
)
def test_proxy(handler: Handler, input: str, expected_output: str) -> None:
    upstream_addr = HostAndPort("localhost", 12345)
    downstream_addr = HostAndPort("localhost", 54321)

    # Starting upstream
    upstream_command_process = [
        "socat",
        f"TCP-LISTEN:{upstream_addr.port},reuseaddr",
        "EXEC:cat!!EXEC:cat",
    ]
    print(f"upstream_command_process: {upstream_command_process}")
    upstream_process = Popen(
        upstream_command_process,
        stdout=PIPE,
        text=True,
    )

    with Proxy(upstream_addr, downstream_addr, handler) as proxy:
        # Connecting to downstream
        downstream_process_command = [
            "socat",
            f"TCP:{downstream_addr}",
            "EXEC:cat!!EXEC:cat",
        ]
        run(
            downstream_process_command,
            input=input,
            text=True,
            check=False,
        )
        proxy.stop()

    # Waiting for upstream to finish
    upstream_process.wait()
    if upstream_process.returncode > 0:
        pass
        #pytest.fail("upstream_process failed")

    assert upstream_process.stdout.readlines() == [expected_output]