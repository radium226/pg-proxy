from typing import Protocol
from typing import Generator, Literal
from dataclasses import dataclass
from contextlib import ExitStack


class Context():
    
    def __init__(self):
        self._exit_stack = ExitStack()


CopyDataAsIs = Literal["passthrough_data"]


@dataclass
class EmitData():

    data: bytes


@dataclass
class UpdateContext():
    
    context: Context


Action = EmitData | CopyDataAsIs | UpdateContext


class Handler[T](Protocol):

    def hande_upstream_data(context: Context, data: T) -> Generator[Action, None, None]:
        ...

    def hande_downstream_data(context: Context, data: T) -> Generator[Action, None, None]:
        ...


class Proxy():
    
    def __init__(self):
        pass