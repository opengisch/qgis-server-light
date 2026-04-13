import logging

from qgis.analysis import QgsNativeAlgorithms

from qgis_server_light.interface.exporter.extract import Algorithm, Output, Parameter
from qgis_server_light.worker.runner.process import algorithm_from_qgs_definition


def test_some_algorithms(qgis_app):
    registry = qgis_app.processingRegistry()
    registry.addProvider(QgsNativeAlgorithms())
    for alg in [
        "native:buffer",
        "native:centroids",
        "native:concavehull",
        "native:rasterlayerproperties",
        "native:rescaleraster",
        "native:collect",
        "native:rasterize",
        "native:affinetransform",
    ]:
        logging.debug(alg)
        algorithm_from_qgs_definition(registry.algorithmById(alg))


def test_algorithm_from_qgs_definition_native_buffer(qgis_app):
    registry = qgis_app.processingRegistry()
    registry.addProvider(QgsNativeAlgorithms())
    buffer = registry.algorithmById("native:buffer")
    assert buffer is not None

    mapped = algorithm_from_qgs_definition(buffer)
    assert mapped == Algorithm(
        id="native:buffer",
        name="buffer",
        display_name="Buffer",
        help_string="",
        parameters=[
            Parameter(
                name="INPUT",
                description="Input layer",
                type="source",
                schema={"type": "string"},
                optional=False,
                default=None,
            ),
            Parameter(
                name="DISTANCE",
                description="Distance",
                type="distance",
                schema={"type": "number"},
                optional=False,
                default=10,
            ),
            Parameter(
                name="SEGMENTS",
                description="Segments",
                type="number",
                schema={"type": "integer", "minimum": 1.0},
                optional=False,
                default=5,
            ),
            Parameter(
                name="END_CAP_STYLE",
                description="End cap style",
                type="enum",
                schema={"type": "string", "enum": ["Round", "Flat", "Square"]},
                optional=False,
                default=0,
            ),
            Parameter(
                name="JOIN_STYLE",
                description="Join style",
                type="enum",
                schema={"type": "string", "enum": ["Round", "Miter", "Bevel"]},
                optional=False,
                default=0,
            ),
            Parameter(
                name="MITER_LIMIT",
                description="Miter limit",
                type="number",
                schema={"type": "number", "minimum": 1.0},
                optional=False,
                default=2,
            ),
            Parameter(
                name="DISSOLVE",
                description="Dissolve result",
                type="boolean",
                schema={"type": "boolean"},
                optional=False,
                default=False,
            ),
            Parameter(
                name="SEPARATE_DISJOINT",
                description="Keep disjoint results separate",
                type="boolean",
                schema={"type": "boolean"},
                optional=False,
                default=False,
            ),
            Parameter(
                name="OUTPUT",
                type="sink",
                schema={"type": "string"},
                optional=False,
                description="Buffered",
            ),
        ],
        outputs=[
            Output(
                name="OUTPUT",
                description="Buffered",
                type="outputVector",
                schema={"type": "string"},
            )
        ],
    )

    assert isinstance(mapped, Algorithm)
    assert mapped.id == buffer.id()
    assert mapped.name == buffer.name()
    assert mapped.display_name == buffer.displayName()

    expected_parameters = [param for param in buffer.parameterDefinitions()]

    assert len(mapped.parameters) == len(expected_parameters)
    assert all(isinstance(param, Parameter) for param in mapped.parameters)
    assert len(mapped.outputs) == len(buffer.outputDefinitions())
