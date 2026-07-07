from dataclasses import dataclass, field

from qgis_server_light.interface.common import BaseInterface


@dataclass(repr=False)
class Attribute(BaseInterface):
    """An attribute belonging to a feature. The aim here is to
    drill down to simple types which can be used in consuming
    applications without further handling. This does not include
    the geometry attribute!

    Attributes:
        name: The name of the attribute. Has to match with the
            name used for exported fields with `Field` class.
        value: Value as simple as possible. It has to be
            [pickleable](https://docs.python.org/3/library/pickle.html#what-can-be-pickled-and-unpickled)

    """

    name: str = field(metadata={"type": "Element"})
    value: int | float | str | bool | bytes | None = field(
        metadata={"type": "Element", "format": "base64"}
    )


@dataclass(repr=False)
class Geometry(Attribute):
    name: str = field(default="geometry", metadata={"type": "Element"})
    value: bytes | None = field(default=None, metadata={"type": "Element", "format": "base64"})

    @property
    def shortened_fields(self) -> set:
        return {"value"}


@dataclass(repr=False)
class Feature(BaseInterface):
    """Feature to hold information of extracted QgsFeature.

    Attributes:
        geometry: The geometry representing the feature.
        attributes: List of attributes defined in this feature.
    """

    geometry: Geometry | None = field(default=None, metadata={"type": "Element"})
    attributes: list[Attribute] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )


@dataclass(repr=False)
class FeatureCollection(BaseInterface):
    """This construction is used to abstract the content of extracted
    features for pickelable transportation from QSL to the queue.
    This way we ensure how things are constructed and transported.

    Attributes:
        name: The name of the feature collection. This is the key to
            match it to requested layers.
        features: The features belonging to the feature collection.
    """

    name: str = field(metadata={"type": "Element"})
    features: list[Feature] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )


@dataclass(repr=False)
class QueryCollection(BaseInterface):
    """Holds all feature collections which are bound to the
    passed queries. The order in the list has to be not changed,
    so that consuming applications can map the response to the
    passed queries.

    Attributes:
        numbers_matched: Information about how many matches are fund for the executed query.
        feature_collections: The feature collections belonging to the passed queries.
    """

    numbers_matched: str | int = field(
        default="unknown",
        metadata={"type": "Element"},
    )
    feature_collections: list[FeatureCollection] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )
