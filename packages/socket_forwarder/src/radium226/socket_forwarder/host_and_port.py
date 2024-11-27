from dataclasses import dataclass


@dataclass
class HostAndPort():

    host: str
    port: int

    def as_tuple(self) -> tuple[str, int]:
        return (self.host, self.port)
    
    @classmethod
    def from_tuple(cls, t: tuple[str, int]) -> "HostAndPort":
        return HostAndPort(*t)
    
    @classmethod
    def parse_address(cls, address: str) -> "HostAndPort":
        host, port = address.split(":")
        return HostAndPort(host, int(port))