from abc import ABC


class Factory(ABC):
    def from_dataclass(self):
        raise NotImplementedError()

    def to_dataclass(self):
        raise NotImplementedError()
