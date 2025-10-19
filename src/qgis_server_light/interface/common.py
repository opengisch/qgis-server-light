"""This module contains common logic, shared beyond all specialized parts of the QGIS-Server-Light interface.

"""
from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from enum import Enum


@dataclass
class BaseInterface:
    """
    This class should be used as base class for all dataclasses in the interface. It offers useful methods to
    handle exposed content in a centralized way. Mainly for logging redaction.

    Since dataclasses gets a __repr__ method installed automatically when they are created, a dataclass
    inheriting from this base class has to be defined as follows:

        ```python
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
        ```

    This way, when an instance of this example class gets logged somewhere it the output will be redacted,
    meaning the logging output might look like this:

        ```
        Config(id=1, secure=**REDACTED**, long_content=abc12...io345)
        ```
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
        Field which contents should get redacted before printing them on the console. This is mainly used to
        prevent passwords in logs.

        Returns:
            The set of field names which should be redacted
        """
        return set()

    @property
    def shortened_fields(self) -> set:
        """
        Fields which should be shortended to a length, this is manly useful for large content fields with
        BLOB etc.

        Returns:
            The set field names which should be shortened.
        """
        return set()

    def __repr__(self):
        members = []
        cls = self.__class__.__name__
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name in self.redacted_fields:
                members.append(f"{field.name}=**REDACTED**")
            elif (
                field.name in self.shortened_fields
                and len(value) > self.shorten_limit * 2
            ):
                members.append(
                    f"{field.name}='{value[:self.shorten_limit]}...{value[((1 + self.shorten_limit) * -1):]}'"
                )
            else:
                members.append(f"{field.name}={value!r}")
        return f"{cls}({', '.join(members)})"


class RedactedString(str):
    """
    This special string class can be used to handle secret strings in the application. It works like a normal
    string but in case its used to print or log its value is not revieled to the output.
    """

    def __new__(cls, value, redacted_text="**REDACTED**"):
        obj = super().__new__(cls, value)
        obj._redacted_text = redacted_text
        return obj

    def __str__(self):
        return self._redacted_text

    def __repr__(self):
        return f"<RedactedString {self._redacted_text}>"

    def reveal(self):
        """
        Allows access to the original value when neccesary.

        Returns:
            The secret string.
        """

        return super().__str__()


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
    host: str = field(metadata={"type": "Element"}, default=None)
    port: int = field(metadata={"type": "Element"}, default=None)
    user: str = field(metadata={"type": "Element"}, default=None)
    dbname: str = field(metadata={"type": "Element"}, default=None)
    password: str = field(metadata={"type": "Element"}, default=None)
    sslmode: SslMode = field(metadata={"type": "Element"}, default=SslMode.PREFER.value)
    application_name: str = field(metadata={"type": "Element"}, default=None)
    client_encoding: str = field(metadata={"type": "Element"}, default="UTF8")
    # possibilitiy to link to another service (nested definitions!)
    service: str = field(metadata={"type": "Element"}, default=None)

    @property
    def redacted_fields(self) -> set:
        return {"password"}
