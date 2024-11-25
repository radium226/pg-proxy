from time import sleep
from threading import Thread
from pendulum import now

from radium226.pg_proxy.server import Server


TIMEOUT_IN_SECONDS = 60

def test_server():
    def stop_thread_target(server: Server):
        sleep(TIMEOUT_IN_SECONDS)
        server.stop()

    begin = now()
    with Server("localhost", 7654) as server:
        stop_thread = Thread(target=stop_thread_target, args=(server, ))
        stop_thread.start()
        server.wait_for()

    stop_thread.join()
    end = now()

    assert (end - begin).in_seconds() == TIMEOUT_IN_SECONDS
    
    