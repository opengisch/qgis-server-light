from abc import ABC
from dataclasses import _MISSING_TYPE, Field, fields
from typing import Any


class DataclassTest(ABC):
    field_defs: list[tuple[str, Any]] = []
    field_defaults: list[tuple[str, Any]] = []
    field_default_factories: list[tuple[str, Any]] = []
    dataclass_to_test: Any

    @property
    def _dataclass_to_test_own_annotations(self) -> dict[str, Field]:
        """

        Returns:
            Dict of annotations which strictly belong to the dataclass_to_test
        """
        return getattr(self.dataclass_to_test, "__annotations__", {})

    @property
    def _dataclass_to_test_own_field_names(self) -> list[str]:
        return [
            f.name
            for f in fields(self.dataclass_to_test)
            if f.name in self._dataclass_to_test_own_annotations
        ]

    @property
    def _dataclass_to_test_own_default_field_names(self):
        return [
            f.name
            for f in fields(self.dataclass_to_test)
            if f.name in self._dataclass_to_test_own_annotations
            and not isinstance(f.default, _MISSING_TYPE)
        ]

    @property
    def _dataclass_to_test_own_default_factory_field_names(self):
        return [
            f.name
            for f in fields(self.dataclass_to_test)
            if f.name in self._dataclass_to_test_own_annotations
            and not isinstance(f.default_factory, _MISSING_TYPE)
        ]

    def test_fields_tested(self):
        """
        With this test we check if we have tested all fields the dataclass has. Since
        we use dataclasses as interface it's important to make tests as picky as
        possible.

        """
        # this ensures we don't check attributes/fields we inherited from parent classes

        assert len(self._dataclass_to_test_own_field_names) == len(
            [name for name, f_type in self.field_defs]
        ), (
            f"Dataclass has untested attributes on "
            f"{self.dataclass_to_test.__module__}.{self.dataclass_to_test.__name__} "
            f"in test {self.__class__.__module__}.{self.__class__.__name__}"
        )

    def test_field_defaults_tested(self):
        """Checks if the dataclass has fields with default value which are not
        tested yet.
        """
        assert len(self._dataclass_to_test_own_default_field_names) == len(
            [name for name, f_type in self.field_defaults]
        ), (
            f"Dataclass has untested default values on "
            f"{self.dataclass_to_test.__module__}.{self.dataclass_to_test.__name__} "
            f"in test {self.__class__.__module__}.{self.__class__.__name__}"
        )

    def test_field_default_factories_tested(self):
        """Checks if the dataclass has fields with default factories which are not
        tested yet.
        """
        assert len(self._dataclass_to_test_own_default_factory_field_names) == len(
            [name for name, f_type in self.field_default_factories]
        ), (
            f"Dataclass has untested default values on "
            f"{self.dataclass_to_test.__module__}.{self.dataclass_to_test.__name__} "
            f"in test {self.__class__.__module__}.{self.__class__.__name__}"
        )

    def test_fields_exist(self):
        for field_name, field_type in self.field_defs:
            assert isinstance(
                self.dataclass_to_test.__dataclass_fields__[field_name], Field
            )

    def test_field_types(self):
        for field_name, field_type in self.field_defs:
            assert (
                self.dataclass_to_test.__dataclass_fields__[field_name].type
                == field_type
            )

    def test_field_default(self):
        for field_name, field_default in self.field_defaults:
            assert (
                self.dataclass_to_test.__dataclass_fields__[field_name].default
                == field_default
            )

    def test_field_default_factory(self):
        for field_name, field_default_factory in self.field_default_factories:
            assert (
                self.dataclass_to_test.__dataclass_fields__[field_name].default_factory
                == field_default_factory
            )

    def test_field_metadata(self):
        for f in fields(self.dataclass_to_test):
            assert "type" in f.metadata
            assert f.metadata["type"] == "Element"
