from contextlib import contextmanager
from typing import Any
from typing import Optional

from PyQt5.QtCore import QDate
from xsdata.formats.converter import Converter
from xsdata.formats.converter import converter


class QDateConverter(Converter):
    format = "yyyy-MM-dd"

    def deserialize(self, value: str, **kwargs: Any) -> QDate:
        return QDate.fromString(value, self.format)

    def serialize(self, value: QDate, **kwargs: Any) -> Optional[str]:
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
        # register further types here
        yield
    finally:
        for tp in registered:
            try:
                converter.unregister_converter(tp)
            except KeyError:
                pass
