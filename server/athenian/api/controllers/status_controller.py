from collections import defaultdict
from contextvars import ContextVar
import time

from aiohttp import web
import prometheus_client

from athenian.api import metadata
from athenian.api.metadata import __package__, __version__
from athenian.api.models.web.versions import Versions
from athenian.api.response import model_response


async def get_versions(request: web.Request) -> web.Response:
    """Return the versions of the backend components."""
    # TODO(vmarkovtsev): add metadata
    model = Versions(api=metadata.__version__)
    return model_response(model)


@web.middleware
async def instrument(request, handler):
    """Middleware to count requests and record the elapsed time."""
    start_time = time.time()
    request.app["request_in_progress"] \
        .labels(__package__, __version__, request.path, request.method) \
        .inc()
    db_elapsed = defaultdict(float)
    request.app["db_elapsed"].set(db_elapsed)
    cache_context = request.app["cache_context"]
    for v in cache_context.values():
        v.set(defaultdict(int))
    try:
        response = await handler(request)  # type: web.Response
        return response
    finally:
        sdb_elapsed, mdb_elapsed, pdb_elapsed = \
            db_elapsed["sdb"], db_elapsed["mdb"], db_elapsed["pdb"]
        try:
            response.headers.add(
                "X-Performance-DB",
                "s %.3f, m %.3f, p %.3f" % (sdb_elapsed, mdb_elapsed, pdb_elapsed))
            for k, v in cache_context.items():
                s = ["%s %d" % (f.replace("athenian.api.", ""), n) for f, n in v.get().items()]
                response.headers.add("X-Performance-Cache-%s" % k.capitalize(), ", ".join(s))
        except NameError:
            pass
        request.app["state_db_latency"] \
            .labels(__package__, __version__, request.path) \
            .observe(sdb_elapsed)
        request.app["metadata_db_latency"] \
            .labels(__package__, __version__, request.path) \
            .observe(mdb_elapsed)
        request.app["precomputed_db_latency"] \
            .labels(__package__, __version__, request.path) \
            .observe(pdb_elapsed)
        request.app["request_in_progress"] \
            .labels(__package__, __version__, request.path, request.method) \
            .dec()
        elapsed = time.time() - start_time
        request.app["request_latency"] \
            .labels(__package__, __version__, request.path) \
            .observe(elapsed)
        request.app["state_db_latency_ratio"] \
            .labels(__package__, __version__, request.path) \
            .observe(sdb_elapsed / elapsed)
        request.app["metadata_db_latency_ratio"] \
            .labels(__package__, __version__, request.path) \
            .observe(mdb_elapsed / elapsed)
        request.app["precomputed_db_latency_ratio"] \
            .labels(__package__, __version__, request.path) \
            .observe(pdb_elapsed / elapsed)
        try:
            code = response.status
        except NameError:
            code = 500
        request.app["request_count"] \
            .labels(__package__, __version__, request.method, request.path, code) \
            .inc()


class StatusRenderer:
    """Render the status page with Prometheus."""

    def __init__(self, registry: prometheus_client.CollectorRegistry):
        """Record the registry where the metrics are maintained."""
        self._registry = registry

    async def __call__(self, request: web.Request) -> web.Response:
        """Endpoint handler to output the current Prometheus state."""
        resp = web.Response(body=prometheus_client.generate_latest(self._registry))
        resp.content_type = prometheus_client.CONTENT_TYPE_LATEST
        return resp


def setup_status(app) -> prometheus_client.CollectorRegistry:
    """Add /status to serve Prometheus-driven runtime metrics."""
    registry = prometheus_client.CollectorRegistry(auto_describe=True)
    app["request_count"] = prometheus_client.Counter(
        "requests_total", "Total Request Count",
        ["app_name", "version", "method", "endpoint", "http_status"],
        registry=registry,
    )
    app["request_latency"] = prometheus_client.Histogram(
        "request_latency_seconds", "Request latency",
        ["app_name", "version", "endpoint"],
        buckets=[0.05, 0.1, 0.25, 0.5, 0.75, 1.0,
                 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0,
                 12.0, 15.0, 20.0, 25.0, 30.0,
                 45.0, 60.0, 120.0, 180.0, 240.0, prometheus_client.metrics.INF],
        registry=registry,
    )
    app["request_in_progress"] = prometheus_client.Gauge(
        "requests_in_progress_total", "Requests in progress",
        ["app_name", "version", "endpoint", "method"],
        registry=registry,
    )
    app["state_db_latency"] = prometheus_client.Histogram(
        "state_db_latency_seconds", "State DB latency",
        ["app_name", "version", "endpoint"],
        registry=registry,
    )
    db_latency_buckets = [
        0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0,
        1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0,
        12.0, 15.0, 20.0, 25.0, 30.0,
        45.0, 60.0, 120.0, 180.0, 240.0, prometheus_client.metrics.INF]
    app["metadata_db_latency"] = prometheus_client.Histogram(
        "metadata_db_latency_seconds", "Metadata DB latency",
        ["app_name", "version", "endpoint"],
        buckets=db_latency_buckets,
        registry=registry,
    )
    app["precomputed_db_latency"] = prometheus_client.Histogram(
        "precomputed_db_latency_seconds", "Precomputed DB latency",
        ["app_name", "version", "endpoint"],
        buckets=db_latency_buckets,
        registry=registry,
    )
    db_ratio_buckets = [
        0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09,
        0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5,
        0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0]
    app["state_db_latency_ratio"] = prometheus_client.Histogram(
        "state_db_latency_ratio", "State DB latency ratio to request time",
        ["app_name", "version", "endpoint"],
        buckets=db_ratio_buckets,
        registry=registry,
    )
    app["metadata_db_latency_ratio"] = prometheus_client.Histogram(
        "metadata_db_latency_ratio", "Metadata DB latency ratio to request time",
        ["app_name", "version", "endpoint"],
        buckets=db_ratio_buckets,
        registry=registry,
    )
    app["precomputed_db_latency_ratio"] = prometheus_client.Histogram(
        "precomputed_db_latency_ratio", "Precomputed DB latency ratio to request time",
        ["app_name", "version", "endpoint"],
        buckets=db_ratio_buckets,
        registry=registry,
    )
    app["db_elapsed"] = ContextVar("db_elapsed", default=None)
    prometheus_client.Info("server", "API server version", registry=registry).info({
        "version": metadata.__version__,
        "commit": getattr(metadata, "__commit__", "null"),
        "build_date": getattr(metadata, "__date__", "null"),
    })
    app.middlewares.insert(0, instrument)
    # passing StatusRenderer(registry) without __call__ triggers a spurious DeprecationWarning
    # FIXME(vmarkovtsev): https://github.com/aio-libs/aiohttp/issues/4519
    app.router.add_get("/status", StatusRenderer(registry).__call__)
    return registry
