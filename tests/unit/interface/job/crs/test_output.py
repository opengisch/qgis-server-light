from qgis_server_light.interface.common import BaseInterface, Crs
from qgis_server_light.interface.job.crs.output import CrsCollection
from tests.base.dataclass_test import DataclassTest


class TestCrsCollection(DataclassTest):
    field_defs = [
        ("crs", list[Crs]),
    ]
    field_default_factories = [
        ("crs", list),
    ]
    dataclass_to_test = CrsCollection

    def test_instantiation(self):
        crs_collection = CrsCollection(crs=[Crs(auth_id="EPSG:4326", axis_inverted=True)])
        assert crs_collection.crs[0].auth_id == "EPSG:4326"

    def test_super(self):
        assert issubclass(CrsCollection, BaseInterface)
