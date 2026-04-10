"""This module contains common logic, shared beyond all specialized parts of the QGIS-Server-Light interface."""

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import List


@dataclass
class BaseInterface:
    """
    This class should be used as base class for all dataclasses in the interface. It offers useful methods to
    handle exposed content in a centralized way. Mainly for logging redaction.

    Since dataclasses gets a __repr__ method installed automatically when they are created, a dataclass
    inheriting from this base class has to be defined as follows:

        @dataclass(repr=False)
        class Config(BaseInterface):
            id: int = field(metadata={"type": "Element"})
            secure: str = field(metadata={"type": "Element"})
            long_content: str = field(metadata={"type": "Element"})

            @property
            def shortened_fields(self) -> set:
                return {"long_content"}

            @property
            def redacted_fields(self) -> set:
                return {"secure"}

    This way, when an instance of this example class gets logged somewhere it the output will be redacted,
    meaning the logging output might look like this:

        Config(id=1, secure=**REDACTED**, long_content=abc12...io345)

    """

    @property
    def shorten_limit(self) -> int:
        """
        The limit to which the content of a field should be shortened.

        Returns:
            The limit.
        """
        return 5

    @property
    def redacted_fields(self) -> set:
        """
        Field which contents should get redacted before printing them on the log. This is mainly used to
        prevent passwords in logs.

        Returns:
            The set of field names which should be redacted
        """
        return set()

    @property
    def shortened_fields(self) -> set:
        """
        Fields which should be shortened to a length, this is manly useful for large content fields with
        BLOB etc.

        Returns:
            The set field names which should be shortened.
        """
        return set()

    def _value_string(self, repr_value: str | bytes):
        return f"{repr_value[: self.shorten_limit]}...{repr_value[((1 + self.shorten_limit) * -1) :]}"

    def _type_aware_value_string(self, value, repr_value):
        value_string = self._value_string(repr_value)
        if type(value) in [str]:
            return f"'{value_string}'"
        else:
            return f"{value_string}"

    def __repr__(self):
        members = []
        cls = self.__class__.__name__
        for obj_field in fields(self):
            # this is the original switch dataclasses allow on fields
            if obj_field.repr:
                value = getattr(self, obj_field.name)
                repr_value = str(value)
                if obj_field.name in self.redacted_fields:
                    members.append(f"{obj_field.name}=**REDACTED**")
                elif (
                    obj_field.name in self.shortened_fields
                    and value is not None
                    and len(repr_value) > self.shorten_limit * 2
                ):
                    members.append(
                        f"{obj_field.name}={self._type_aware_value_string(value, repr_value)}"
                    )
                else:
                    members.append(f"{obj_field.name}={value!r}")
        return f"{cls}({', '.join(members)})"


class RedactedString:
    """
    This special string class can be used to handle secret strings in the application. It works like a normal
    string but in case it's used to print or log its value is not reveled to the output.
    """

    def __init__(self, value, redacted_text="**REDACTED**"):
        self._value = value
        self._redacted_text = redacted_text

    def __str__(self):
        return self._redacted_text

    def __repr__(self):
        return f"<RedactedString {self._redacted_text}>"

    def __format__(self, format_spec):
        return self._redacted_text

    def __json__(self):
        return self._redacted_text

    def reveal(self):
        """
        Allows access to the original value when necessary.

        Returns:
            The secret string.
        """

        return self._value


class SslMode(str, Enum):
    DISABLE = "disable"
    ALLOW = "allow"
    PREFER = "prefer"
    REQUIRE = "require"
    VERIFY_CA = "verify-ca"
    VERIFY_FULL = "verify-full"


@dataclass(repr=False)
class PgServiceConf(BaseInterface):
    """
    A typed definition of the pg_service.conf definition which might be used.
    """

    name: str = field(metadata={"type": "Element"})
    host: str | None = field(
        default=None,
        metadata={"type": "Element"},
    )
    port: int | None = field(default=None, metadata={"type": "Element"})
    user: str | None = field(default=None, metadata={"type": "Element"})
    dbname: str | None = field(default=None, metadata={"type": "Element"})
    password: str | None = field(default=None, metadata={"type": "Element"})
    sslmode: SslMode = field(default=SslMode.PREFER, metadata={"type": "Element"})
    application_name: str | None = field(default=None, metadata={"type": "Element"})
    client_encoding: str = field(default="UTF8", metadata={"type": "Element"})
    # possibilitiy to link to another service (nested definitions!)
    service: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def redacted_fields(self) -> set:
        return {"password"}


@dataclass(repr=False)
class BBox(BaseInterface):
    x_min: float = field(metadata={"type": "Element"})
    x_max: float = field(metadata={"type": "Element"})
    y_min: float = field(metadata={"type": "Element"})
    y_max: float = field(metadata={"type": "Element"})
    z_min: float = field(default=0.0, metadata={"type": "Element"})
    z_max: float = field(default=0.0, metadata={"type": "Element"})

    def to_list(self) -> list:
        return [self.x_min, self.y_min, self.z_min, self.x_max, self.y_max, self.z_max]

    def to_string(self) -> str:
        return ",".join([str(item) for item in self.to_list()])

    def to_2d_list(self) -> list:
        return [self.x_min, self.y_min, self.x_max, self.y_max]

    def to_2d_string(self) -> str:
        return ",".join([str(item) for item in self.to_2d_list()])

    @staticmethod
    def from_string(bbox_string: str) -> "BBox":
        """
        Takes a CSV string representation of a BBox in the form:
            '<x_min>,<y_min>,<x_max>,<y_max>' or
            '<x_min>,<y_min>,<z_min>,<x_max>,<y_max>,<z_max>'
        """
        coordinates = bbox_string.split(",")
        if len(coordinates) == 4:
            return BBox(
                x_min=float(coordinates[0]),
                y_min=float(coordinates[1]),
                x_max=float(coordinates[2]),
                y_max=float(coordinates[3]),
            )
        elif len(coordinates) == 6:
            return BBox(
                x_min=float(coordinates[0]),
                y_min=float(coordinates[1]),
                z_min=float(coordinates[2]),
                x_max=float(coordinates[3]),
                y_max=float(coordinates[4]),
                z_max=float(coordinates[5]),
            )
        else:
            raise ValueError(f"Invalid bbox string: {bbox_string}")

    @staticmethod
    def from_list(bbox_list: List[float]) -> "BBox":
        """
        Takes a list representation of a BBox in the form:
            [<x_min>,<y_min>,<x_max>,<y_max>] or
            [<x_min>,<y_min>,<z_min>,<x_max>,<y_max>,<z_max>]
        """
        if len(bbox_list) == 4:
            return BBox(
                x_min=bbox_list[0],
                y_min=bbox_list[1],
                x_max=bbox_list[2],
                y_max=bbox_list[3],
            )
        elif len(bbox_list) == 6:
            return BBox(
                x_min=bbox_list[0],
                y_min=bbox_list[1],
                z_min=bbox_list[2],
                x_max=bbox_list[3],
                y_max=bbox_list[4],
                z_max=bbox_list[5],
            )
        else:
            raise ValueError(f"Invalid bbox list: {bbox_list}")


@dataclass(repr=False)
class Style(BaseInterface):
    name: str = field(metadata={"type": "Element"})
    definition: str = field(metadata={"type": "Element"})

    @property
    def shortened_fields(self) -> set:
        return {"definition"}
