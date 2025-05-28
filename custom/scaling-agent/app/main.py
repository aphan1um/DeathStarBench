from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from util import execute_promql_query, parse_promql_response_by_service

import logging
import time

TIME_OFFSET = 5
ALL_SERVICES = None

app = FastAPI()
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S"
)

# TODO: Invoke K8s API to scale
# config.load_incluster_config()

@app.get('/service/metrics')
async def get_service_metrics(request: Request):
    query_timestamp = int(time.time() - TIME_OFFSET)

    # used to define state space
    services_cpu = parse_promql_response_by_service(execute_promql_query(
      'sum by (container) (rate(container_cpu_usage_seconds_total{namespace="default"}[1m])) / sum by (container) (kube_pod_container_resource_requests{namespace="default", resource="cpu"})',
      query_timestamp
    ))

    services_mem = parse_promql_response_by_service(execute_promql_query(
      'sum by (container) (avg_over_time(container_memory_working_set_bytes{namespace="default"}[35s])) / sum by (container) (kube_pod_container_resource_requests{namespace="default", resource="memory"})',
      query_timestamp
    ))

    if ALL_SERVICES is None:
      ALL_SERVICES = sorted(services_cpu.keys())
      logging.info('Obtained services for the first time: [' + ','.join(ALL_SERVICES) + ']')

    # to be used to calculate rewards
    raw_tps = parse_promql_get_value(execute_promql_query(
      'sum(rate(nginx_http_requests_total[35s]))',
      query_timestamp
    ))

    raw_tps_success = parse_promql_get_value(execute_promql_query(
      'sum(rate(nginx_http_requests_total{status=~"2.*"}[35s]))/sum(rate(nginx_http_requests_total[35s]))',
      query_timestamp
    ))

    return JSONResponse(content = {
        'services': [
          [
            round(float(services_cpu[svc], 4)),
            round(float(services_mem[svc]), 4)
          ]
          for svc in ALL_SERVICES
        ],
        'tps': int(raw_tps),
        'tps_success': int(raw_tps_success)
    })
