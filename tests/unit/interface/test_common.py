import io
import logging
import math
from contextlib import redirect_stdout
from dataclasses import dataclass, field

import pytest

from qgis_server_light.interface.common import (
    BaseInterface,
    BBox,
    Crs,
    RedactedString,
    Style,
)
from tests.base.dataclass_test import DataclassTest


class TestBaseInterface:
    def test_properties(self):
        bi = BaseInterface()
        assert bi.shorten_limit == 5
        assert isinstance(bi.redacted_fields, set)
        assert isinstance(bi.shortened_fields, set)

    def test_redacted(self):
        @dataclass(repr=False)
        class Test(BaseInterface):
            text: str = field(default=None)

            @property
            def redacted_fields(self) -> set:
                return {"text"}

        t = Test(text="secret")
        assert t.__repr__() == "Test(text=**REDACTED**)"

    @pytest.mark.parametrize(
        "value,expected_result",
        [
            (
                "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod",
                "Test(long_field='Lorem...eirmod')",
            ),
            (
                10000000000000000000000000000000000000000000000000000000000000,
                "Test(long_field=10000...000000)",
            ),
            (
                10.111111111111111111111111111111111,
                "Test(long_field=10.11...111111)",
            ),
            (
                b"Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod",
                "Test(long_field=b'Lor...irmod')",
            ),
            (
                bytes(10),
                "Test(long_field=b'\\x0...0\\x00')",
            ),
        ],
    )
    def test_shortened(self, value, expected_result):
        @dataclass(repr=False)
        class Test(BaseInterface):
            long_field: str | int | float | bytes = field(default=None)

            @property
            def shortened_fields(self) -> set:
                return {"long_field"}

        t = Test(
            long_field=value,
        )
        assert t.__repr__() == expected_result

    def test_hidden(self):
        @dataclass(repr=False)
        class Test(BaseInterface):
            hidden_field: str = field(default=None, repr=False)

        t = Test(
            hidden_field="hidden value",
        )
        assert t.__repr__() == "Test()"

    def test_regular(self):
        @dataclass(repr=False)
        class Test(BaseInterface):
            regular_field: str = field(default=None)

        t = Test(
            regular_field="regular value",
        )
        assert t.__repr__() == "Test(regular_field='regular value')"


class TestRedactedString:
    def test_str(self):
        s = RedactedString("test")
        assert s.__str__() == "**REDACTED**"
        assert str(s) == "**REDACTED**"

    def test_repr(self):
        s = RedactedString("test")
        assert s.__repr__() == "<RedactedString **REDACTED**>"
        assert repr(s) == "<RedactedString **REDACTED**>"

    def test_reveal(self):
        assert RedactedString("test").reveal() == "test"

    def test_print(self):
        s = RedactedString("test")
        f = io.StringIO()
        with redirect_stdout(f):
            print(s)

        output = f.getvalue().strip()
        assert output == "**REDACTED**"

    def test_logging(self, caplog):
        logger = logging.getLogger("test")
        s = RedactedString("secret")

        with caplog.at_level(logging.INFO):  # noqa: F821
            logger.info("Value: %s", s)

        assert "Value: **REDACTED**" in caplog.text
        assert "secret" not in caplog.text

    def test_fstring_is_redacted(self):
        s = RedactedString("secret")

        assert f"{s}" == "**REDACTED**"

    def test_custom_redacted_text(self):
        s = RedactedString("secret", redacted_text="XXX")

        assert str(s) == "XXX"
        assert repr(s) == "<RedactedString XXX>"

    def test_container(self):
        s = RedactedString("test")
        f = io.StringIO()
        with redirect_stdout(f):
            print([s])

        output = f.getvalue().strip()
        assert output == "[<RedactedString **REDACTED**>]"


class TestBBox(DataclassTest):
    field_defs = [
        ("x_min", float),
        ("x_max", float),
        ("y_min", float),
        ("y_max", float),
        ("z_min", float),
        ("z_max", float),
    ]
    field_defaults = [
        ("z_min", 0.0),
        ("z_max", 0.0),
    ]
    dataclass_to_test = BBox

    def test_instantiation(self):
        bbox = BBox(x_min=1, y_min=2, x_max=3, y_max=4)
        assert bbox.x_min == 1
        assert bbox.y_min == 2
        assert math.isclose(bbox.z_min, 0.0)  # default
        assert math.isclose(bbox.z_max, 0.0)

    # to_list / to_2d_list
    def test_to_list_methods(self):
        bbox = BBox(x_min=1, y_min=2, z_min=3, x_max=4, y_max=5, z_max=6)
        assert bbox.to_list() == [1, 2, 3, 4, 5, 6]
        assert bbox.to_2d_list() == [1, 2, 4, 5]

    def test_to_string_methods(self):
        bbox = BBox(x_min=1, y_min=2, z_min=3, x_max=4, y_max=5, z_max=6)
        assert bbox.to_string() == "1,2,3,4,5,6"
        assert bbox.to_2d_string() == "1,2,4,5"

    # from_string factory
    def test_from_string_2d(self):
        s = "1,2,4,5"
        bbox = BBox.from_string(s)
        assert bbox.to_2d_list() == [1, 2, 4, 5]
        assert math.isclose(bbox.z_min, 0.0)
        assert math.isclose(bbox.z_max, 0.0)

    def test_from_string_3d(self):
        s = "1,2,3,4,5,6"
        bbox = BBox.from_string(s)
        assert bbox.to_list() == [1, 2, 3, 4, 5, 6]

    def test_from_string_invalid(self):
        with pytest.raises(ValueError):
            BBox.from_string("1,2,3")

    # from_list factory
    def test_from_list_2d(self):
        coords = [1, 2, 4, 5]
        bbox = BBox.from_list(coords)
        assert bbox.to_2d_list() == [1, 2, 4, 5]
        assert math.isclose(bbox.z_min, 0.0)
        assert math.isclose(bbox.z_max, 0.0)

    def test_from_list_3d(self):
        coords = [1, 2, 3, 4, 5, 6]
        bbox = BBox.from_list(coords)
        assert bbox.to_list() == [1, 2, 3, 4, 5, 6]

    def test_from_list_invalid(self):
        with pytest.raises(ValueError):
            BBox.from_list([1, 2, 3])


class TestCrs(DataclassTest):
    field_defs = [
        ("auth_id", str),
        ("postgis_srid", int),
        ("ogc_uri", str),
        ("ogc_urn", str),
        ("axis_inverted", bool),
    ]
    field_defaults = [
        ("auth_id", None),
        ("postgis_srid", None),
        ("ogc_uri", None),
        ("ogc_urn", None),
        ("axis_inverted", False),
    ]
    dataclass_to_test = Crs

    def test_instantiation(self):
        crs = Crs(
            auth_id="EPSG:4326",
            postgis_srid=4326,
            ogc_uri="http://www.opengis.net/def/crs/EPSG/0/4326",
            ogc_urn="urn:ogc:def:crs:EPSG::4326",
            axis_inverted=True,
        )
        assert crs.auth_id == "EPSG:4326"
        assert crs.axis_inverted is True

    def test_axis_inverted_default(self):
        assert Crs(auth_id="EPSG:2056").axis_inverted is False


class TestStyle(DataclassTest):
    field_defs = [
        ("name", str),
        ("definition", str),
    ]
    dataclass_to_test = Style

    def test_instantiation(self):
        style = Style(name="test", definition="abcd")
        assert style.name == "test"
        assert style.definition == "abcd"

    def test_configured_shortened_fields(self):
        style = Style(name="test", definition="abcd")
        assert style.shortened_fields == {"definition"}
