import asyncio
import pickle

import pytest
from xsdata.formats.dataclass.serializers import JsonSerializer
from xsdata.formats.dataclass.serializers.dict import DictFactory

from qgis_server_light.dispatcher.redis_asio import RedisQueue, derive_job_info, job_info_classes
from qgis_server_light.interface.common import BBox
from qgis_server_light.interface.dispatcher.common import Status
from qgis_server_light.interface.job.common.input import QslJobParameter
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.feature.input import (
    QslJobInfoFeature,
    QslJobParameterFeature,
)
from qgis_server_light.interface.job.feature_info.input import (
    QslJobInfoFeatureInfo,
    QslJobParameterFeatureInfo,
)
from qgis_server_light.interface.job.legend.input import (
    QslJobInfoLegend,
    QslJobParameterLegend,
)
from qgis_server_light.interface.job.process.description import (
    InputDescription,
    ProcessDescription,
    ProcessDescriptions,
    Schema,
)
from qgis_server_light.interface.job.process.input import (
    ParameterInput,
    QslJobParameterExecuteProcess,
)
from qgis_server_light.interface.job.render.input import (
    QslJobInfoRender,
    QslJobParameterRender,
)


class TestDeriveJobInfo:
    @pytest.mark.parametrize(
        "job_parameter,expected_class",
        [
            (
                QslJobParameterRender(
                    layers=[],
                    bbox=BBox(x_min=0.0, x_max=1.0, y_min=0.0, y_max=1.0),
                    crs="EPSG:2056",
                    width=256,
                    height=256,
                ),
                QslJobInfoRender,
            ),
            (
                QslJobParameterFeatureInfo(
                    INFO_FORMAT="application/json", QUERY_LAYERS="a", I="1", J="1"
                ),
                QslJobInfoFeatureInfo,
            ),
            (QslJobParameterLegend(layers=[]), QslJobInfoLegend),
            (QslJobParameterFeature(queries=[]), QslJobInfoFeature),
        ],
    )
    def test_supported(self, job_parameter, expected_class):
        job_info = derive_job_info("my_cool_id", job_parameter)
        assert isinstance(job_info, expected_class)
        assert job_info.id == "my_cool_id"
        assert job_info.type == expected_class.__name__
        assert job_info.job is job_parameter

    def test_unsupported(self):
        with pytest.raises(TypeError, match="Unsupported runner type"):
            derive_job_info("blabla", QslJobParameter())


class FakePipeline:
    def __init__(self, calls: list):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def hset(self, key, field, value):
        self.calls.append(("hset", key, field))

    async def rpush(self, name, value):
        self.calls.append(("rpush", name, value))

    async def execute(self):
        self.calls.append(("execute",))


class FakePubSub:
    def __init__(self, calls: list):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def subscribe(self, channel):
        self.calls.append(("subscribe", channel))

    async def get_message(self, timeout, ignore_subscribe_messages):
        job_id = next(call[2] for call in self.calls if call[0] == "rpush")
        return {"data": pickle.dumps(JobResult(id=job_id, data=b"", content_type="image/png"))}


class FakeRedisClient:
    def __init__(self):
        self.calls = []
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    def pipeline(self):
        return FakePipeline(self.calls)

    def pubsub(self):
        return FakePubSub(self.calls)

    async def hget(self, key, field):
        return Status.SUCCESS.value.encode()

    async def delete(self, key):
        self.calls.append(("delete", key))


class TestRedisQueue:
    def test_protocol(self):
        assert RedisQueue.job_queue_name == "jobs"
        assert RedisQueue.job_key("my_cool_id") == "job:my_cool_id"
        assert RedisQueue.channel("my_cool_id") == "notifications:my_cool_id"

    def test_post_subscribes_before_queuing(self):
        client = FakeRedisClient()
        result, status = asyncio.run(RedisQueue(client).post(QslJobParameterLegend(layers=[])))
        assert status == Status.SUCCESS.value
        names = [call[0] for call in client.calls]
        assert names.index("subscribe") < names.index("rpush")

    def test_post_sets_queued_status_in_queuing_transaction(self):
        client = FakeRedisClient()
        asyncio.run(RedisQueue(client).post(QslJobParameterLegend(layers=[])))
        job_id = next(call[2] for call in client.calls if call[0] == "rpush")
        job_key = RedisQueue.job_key(job_id)
        status_index = client.calls.index(("hset", job_key, RedisQueue.job_status_key))
        rpush_index = next(index for index, call in enumerate(client.calls) if call[0] == "rpush")
        execute_indexes = [index for index, call in enumerate(client.calls) if call[0] == "execute"]
        assert execute_indexes == [rpush_index + 1]
        assert status_index < rpush_index

    @pytest.mark.parametrize("job_info_class", job_info_classes.values())
    def test_queue_for_every_job_info(self, job_info_class):
        assert RedisQueue.queue_name(job_info_class.__name__)

    @pytest.mark.parametrize(
        "job_parameter,expected_queue_name",
        [
            (QslJobParameterLegend(layers=[]), "jobs"),
            (
                QslJobParameterExecuteProcess(
                    process_id="native:centroids",
                    parameters=[ParameterInput("ALL_PARTS", False)],
                ),
                "jobs:process",
            ),
        ],
    )
    def test_post_routes_to_queue_of_job_type(self, job_parameter, expected_queue_name):
        client = FakeRedisClient()
        asyncio.run(RedisQueue(client).post(job_parameter))
        queue_names = [call[1] for call in client.calls if call[0] == "rpush"]
        assert queue_names == [expected_queue_name]


class TestProcessRegistry:
    def test_protocol(self):
        assert RedisQueue.process_registry_key == "processes"

    def test_process_descriptions_empty_without_registry(self):
        client = FakeRedisClient()
        assert asyncio.run(RedisQueue(client).process_descriptions()) == ProcessDescriptions()

    @pytest.mark.parametrize(
        "process_descriptions",
        [
            ProcessDescriptions(
                processes=[
                    ProcessDescription(
                        id="native:centroids",
                        title="Centroids",
                        inputs=[
                            InputDescription(
                                id="ALL_PARTS",
                                title="Create centroid for each part",
                                schema=Schema(type="boolean", default=False),
                            )
                        ],
                    )
                ]
            )
        ],
    )
    def test_process_descriptions(self, process_descriptions):
        client = FakeRedisClient()
        client.values[RedisQueue.process_registry_key] = (
            JsonSerializer(dict_factory=DictFactory.FILTER_NONE)
            .render(process_descriptions)
            .encode()
        )
        assert asyncio.run(RedisQueue(client).process_descriptions()) == process_descriptions
