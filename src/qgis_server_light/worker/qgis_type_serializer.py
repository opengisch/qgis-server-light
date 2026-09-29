import contextlib
from contextlib import contextmanager
from typing import Any

from PyQt5.QtCore import QDate, QDateTime, Qt
from xsdata.formats.converter import Converter, converter


class QDateConverter(Converter):
    format = "yyyy-MM-dd"

    def deserialize(self, value: str, **kwargs: Any) -> QDate:
        return QDate.fromString(value, self.format)

    def serialize(self, value: QDate, **kwargs: Any) -> str | None:
        if value:
            return value.toString(self.format)
        else:
            return None


class QDateTimeConverter(Converter):
    format = Qt.DateFormat.ISODate

    def deserialize(self, value: str, **kwargs: Any) -> QDateTime:
        return QDateTime.fromString(value, self.format)

    def serialize(self, value: QDateTime, **kwargs: Any) -> str | None:
        if value:
            return value.toString(self.format)
        else:
            return None


@contextmanager
def register_converters_at_runtime():
    def register(custom_type, converter_instance, registered_types):
        converter.register_converter(custom_type, converter_instance)
        registered_types.append(custom_type)

    registered = []
    try:
        register(QDate, QDateConverter(), registered)
        register(QDateTime, QDateTimeConverter(), registered)
        # register further types here
        yield
    finally:
        for tp in registered:
            with contextlib.suppress(KeyError):
                converter.unregister_converter(tp)
