from dataclasses import dataclass
from typing import Any, assert_never



@dataclass
class EmitData():
    
    data: bytes


@dataclass
class PassThroughData():
    pass


@dataclass
class UpdateContext():
    
    context: dict[str, Any]


Action = EmitData | PassThroughData | UpdateContext


actions: list[Action] = [
    EmitData(b"Hello World"),
    PassThroughData(),
    UpdateContext({"key": "value"})
]

for action in actions:
    match action:
        case EmitData(data=data):
            print(f"Emitting data: {data}")
        case PassThroughData():
            print("Passing through data")
        case UpdateContext(context=new_context):
            print(f"Updating context: {new_context}")
        case _:
            assert_never(action)

