import logging
from collections.abc import Iterator, MutableMapping
from time import monotonic

from qgis.core import QgsMapLayer

DEFAULT_TTL_SECONDS = 24 * 60 * 60


class LayerCache(MutableMapping[str, QgsMapLayer]):
    """Layers opened by the worker, shared by all jobs of the worker process.

    Entries which were not used for longer than the TTL are evicted by
    `evict_expired`. This bounds the growth caused by layers which are not
    requested anymore (e.g. after a project was changed). It does not bound the
    number of layers used within one TTL.

    Not thread safe: only the thread processing the jobs may access it.
    """

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._layers: dict[str, QgsMapLayer] = {}
        self._last_used: dict[str, float] = {}

    def __getitem__(self, cache_name: str) -> QgsMapLayer:
        layer = self._layers[cache_name]
        self._last_used[cache_name] = monotonic()
        return layer

    def __setitem__(self, cache_name: str, layer: QgsMapLayer) -> None:
        self._layers[cache_name] = layer
        self._last_used[cache_name] = monotonic()

    def __delitem__(self, cache_name: str) -> None:
        del self._layers[cache_name]
        del self._last_used[cache_name]

    def __contains__(self, cache_name: object) -> bool:
        return cache_name in self._layers

    def __iter__(self) -> Iterator[str]:
        return iter(self._layers)

    def __len__(self) -> int:
        return len(self._layers)

    def evict_expired(self) -> int:
        """Evicts all layers which were not used within the TTL.

        Returns:
            The number of evicted layers.
        """
        expired_before = monotonic() - self.ttl_seconds
        expired = [name for name, used in self._last_used.items() if used < expired_before]
        for cache_name in expired:
            del self[cache_name]
        if expired:
            # cache names contain the layer source (credentials), they are not logged
            logging.info(
                f"Evicted {len(expired)} layers unused for more than {self.ttl_seconds}s "
                f"from cache, {len(self)} layers remain"
            )
        return len(expired)
