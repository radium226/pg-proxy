from time import sleep
from functools import wraps

def retry(wait: int = 1, times: int | None = 3, reraise: bool = True):
    """ Decorator retries a function if an exception is raised during function
    invocation, to an arbitrary limit.
    :param wait: int, time in seconds to wait to try again
    :param retries: int, number of times to retry function. If None, unlimited
        retries.
    :param reraise: bool, re-raises the last caught exception if true
    """
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            tries = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    tries += 1
                    if tries <= times or times is None:
                        sleep(wait)
                    else:
                        break
            if reraise:
                raise
        return wrapped
    return decorator