from qgis.analysis import QgsNativeAlgorithms

from qgis_server_light.interface.exporter.extract import (
    Algorithm,
    Output,
    Parameter,
    ProcessingParameterTypeBoolean,
    ProcessingParameterTypeEnum,
    ProcessingParameterTypeFloat,
    ProcessingParameterTypeInt,
    ProcessingParameterTypeVectorLayer,
)
from qgis_server_light.worker.runner.process import algorithm_from_qgs_definition


def test_some_algorithms(qgis_app):
    registry = qgis_app.processingRegistry()
    registry.addProvider(QgsNativeAlgorithms())
    for alg_name in [
        "native:buffer",
        "native:centroids",
        "native:concavehull",
        "native:rasterlayerproperties",
        "native:rescaleraster",
        "native:collect",
        "native:rasterize",
        "native:affinetransform",
    ]:
        algorithm = registry.algorithmById(alg_name)
        assert algorithm is not None, alg_name
        algorithm_from_qgs_definition(algorithm)


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
                type=ProcessingParameterTypeVectorLayer(),
                optional=False,
                default=None,
                is_destination=False,
            ),
            Parameter(
                name="DISTANCE",
                description="Distance",
                type=ProcessingParameterTypeFloat(),
                optional=False,
                default=10,
                is_destination=False,
            ),
            Parameter(
                name="SEGMENTS",
                description="Segments",
                type=ProcessingParameterTypeInt(minimum=1),
                optional=False,
                default=5,
                is_destination=False,
            ),
            Parameter(
                name="END_CAP_STYLE",
                description="End cap style",
                type=ProcessingParameterTypeEnum(
                    options=[
                        "Round",
                        "Flat",
                        "Square",
                    ]
                ),
                optional=False,
                default=0,
                is_destination=False,
            ),
            Parameter(
                name="JOIN_STYLE",
                description="Join style",
                type=ProcessingParameterTypeEnum(
                    options=[
                        "Round",
                        "Miter",
                        "Bevel",
                    ]
                ),
                optional=False,
                default=0,
                is_destination=False,
            ),
            Parameter(
                name="MITER_LIMIT",
                description="Miter limit",
                type=ProcessingParameterTypeFloat(minimum=1.0),
                optional=False,
                default=2,
                is_destination=False,
            ),
            Parameter(
                name="DISSOLVE",
                description="Dissolve result",
                type=ProcessingParameterTypeBoolean(),
                optional=False,
                default=False,
                is_destination=False,
            ),
            Parameter(
                name="SEPARATE_DISJOINT",
                description="Keep disjoint results separate",
                type=ProcessingParameterTypeBoolean(),
                optional=False,
                default=False,
                is_destination=False,
            ),
            Parameter(
                name="OUTPUT",
                type=ProcessingParameterTypeVectorLayer(),
                optional=False,
                description="Buffered",
                default=None,
                is_destination=True,
            ),
        ],
        outputs=[
            Output(
                name="OUTPUT",
                description="Buffered",
                type=ProcessingParameterTypeVectorLayer(),
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
