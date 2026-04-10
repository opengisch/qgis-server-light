from qgis_server_light.interface.common import BaseInterface
from qgis_server_light.interface.job.feature.output import (
    Attribute,
    Feature,
    FeatureCollection,
    Geometry,
    QueryCollection,
)
from tests.base.dataclass_test import DataclassTest


class TestAttribute(DataclassTest):
    field_defs = [
        ("name", str),
        ("value", int | float | str | bool | bytes | None),
    ]
    dataclass_to_test = Attribute

    def test_instantiation(self):
        attribute = Attribute(name="test", value=1)
        assert attribute.name == "test"
        assert attribute.value == 1

    def test_super(self):
        assert issubclass(Attribute, BaseInterface)


class TestGeometry(DataclassTest):
    field_defs = [
        ("name", str),
        ("value", bytes | None),
    ]
    field_defaults = [
        ("name", "geometry"),
        ("value", None),
    ]
    dataclass_to_test = Geometry

    def test_instantiation(self):
        attribute = Geometry(name="test", value=b"1")
        assert attribute.name == "test"
        assert attribute.value == b"1"

    def test_super(self):
        assert issubclass(Geometry, Attribute)

    def test_shortened_fields(self):
        attribute = Geometry(name="test", value=b"1")
        assert attribute.shortened_fields == {"value"}


class TestFeature(DataclassTest):
    field_defs = [("geometry", Geometry | None), ("attributes", list[Attribute])]
    field_defaults = [
        ("geometry", None),
    ]
    field_default_factories = [("attributes", list)]
    dataclass_to_test = Feature

    def test_instantiation(self):
        attribute = Attribute(name="test", value=1)
        geometry = Geometry(name="geom", value=b"abcd")
        feature = Feature(geometry=geometry, attributes=[attribute])
        assert isinstance(feature.geometry, Geometry)
        assert isinstance(feature.geometry.value, bytes)
        assert isinstance(feature.attributes, list)
        assert isinstance(feature.attributes[0], Attribute)

    def test_super(self):
        assert issubclass(Feature, BaseInterface)


class TestFeatureCollection(DataclassTest):
    field_defs = [("name", str), ("features", list[Feature])]
    field_default_factories = [("features", list)]
    dataclass_to_test = FeatureCollection

    def test_instantiation(self):
        attribute = Attribute(name="test", value=1)
        geometry = Attribute(name="geom", value=b"abcd")
        feature = Feature(geometry=geometry, attributes=[attribute])
        feature_collection = FeatureCollection(
            name="test_layer",
            features=[feature],
        )
        assert feature_collection.name == "test_layer"
        assert isinstance(feature_collection.features, list)
        assert isinstance(feature_collection.features[0], Feature)

    def test_super(self):
        assert issubclass(FeatureCollection, BaseInterface)


class TestQueryCollection(DataclassTest):
    field_defs = [
        ("numbers_matched", str | int),
        ("feature_collections", list[FeatureCollection]),
    ]
    field_defaults = [("numbers_matched", "unknown")]
    field_default_factories = [("feature_collections", list)]
    dataclass_to_test = QueryCollection

    def test_instantiation(self):
        attribute = Attribute(name="test", value=1)
        geometry = Attribute(name="geom", value=b"abcd")
        feature = Feature(geometry=geometry, attributes=[attribute])
        feature_collection = FeatureCollection(
            name="test_layer",
            features=[feature],
        )
        assert feature_collection.name == "test_layer"
        assert isinstance(feature_collection.features, list)
        assert isinstance(feature_collection.features[0], Feature)

    def test_super(self):
        assert issubclass(FeatureCollection, BaseInterface)
