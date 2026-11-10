import pytest

from qgis_server_light.worker import layer_cache as layer_cache_module
from qgis_server_light.worker.layer_cache import LayerCache


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(layer_cache_module, "monotonic", clock)
    yield clock


@pytest.fixture
def cache(clock):
    yield LayerCache(ttl_seconds=100)


def test_evicts_layers_unused_longer_than_ttl(cache, clock):
    cache["a"] = "layer a"
    clock.now += 101

    assert cache.evict_expired() == 1
    assert cache == {}


def test_keeps_layers_within_ttl(cache, clock):
    cache["a"] = "layer a"
    clock.now += 100

    assert cache.evict_expired() == 0
    assert cache == {"a": "layer a"}


def test_access_renews_ttl(cache, clock):
    cache["a"] = "layer a"
    cache["b"] = "layer b"
    clock.now += 60
    assert cache["a"] == "layer a"
    clock.now += 60

    assert cache.evict_expired() == 1
    assert cache == {"a": "layer a"}


def test_membership_check_does_not_renew_ttl(cache, clock):
    cache["a"] = "layer a"
    clock.now += 60
    assert "a" in cache
    clock.now += 60

    cache.evict_expired()
    assert "a" not in cache


def test_pop_removes_layer(cache, clock):
    cache["a"] = "layer a"
    assert cache.pop("a") == "layer a"
    assert cache.pop("a", None) is None

    clock.now += 101
    assert cache.evict_expired() == 0
