from prometheus_client import Counter, generate_latest

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


def generate_latest_metrics():
    """Generate Latest."""
    return generate_latest()
