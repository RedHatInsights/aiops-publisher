from prometheus_client import Counter, generate_latest
from prometheus_client import CollectorRegistry, multiprocess


# Prometheus Metrics
METRICS = {
    'posts': Counter(
        'aiops_publisher_post_requests_total',
        'The total number of post data requests'
    ),
    'post_successes': Counter(
        'aiops_publisher_post_requests_successful',
        'The total number of successful post data requests'
    ),
    'post_errors': Counter(
        'aiops_publisher_post_requests_exceptions',
        'The total number of post data request exceptions'
    ),
}


def generate_aggregated_metrics():
    """Generate Aggregated Metrics for multiple processes."""
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return generate_latest(registry)
