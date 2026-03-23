from abc import ABC
from enum import Enum
from typing import Any


class EnumTest(ABC):
    enum_names: set[str]
    enum_values: set[Any]
    enum_class_to_test: Enum

    def test_enum_members_names(self):
        actual_names = {c.name for c in self.enum_class_to_test}
        assert actual_names == self.enum_names

    def test_enum_values(self):
        actual_values = {c.value for c in self.enum_class_to_test}
        assert actual_values == self.enum_values
