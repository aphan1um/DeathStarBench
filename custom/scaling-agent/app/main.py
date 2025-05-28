from kubernetes import client, config
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from util import execute_promql_query, parse_promql_response_by_service, parse_promql_get_value

import logging
import math
import os
import time

TIME_OFFSET = 5
ALL_SERVICES = None
ALL_SERVICES_MAX_REPLICAS = int(os.getenv('ALL_SERVICES_MAX_REPLICAS'))

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S"
)

# retrieve some resource data from Kubernetes before server initialises
@asynccontextmanager
async def lifespan(app: FastAPI):
  global ALL_SERVICES

  config.load_incluster_config()
  apps_v1 = client.AppsV1Api()

  k8s_deployments = apps_v1.list_namespaced_deployment(namespace="default").items
  ALL_SERVICES = sorted([d.metadata.name for d in k8s_deployments])
  logging.info('Obtained services: [' + ','.join(ALL_SERVICES) + ']')

  logging.info('Maximum amount of pods per service: ' + ALL_SERVICES_MAX_REPLICAS)
  yield

app = FastAPI(lifespan=lifespan)

@app.get('/service/metrics')
async def get_service_metrics(request: Request):
    global ALL_SERVICES
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

    # to be also used calculate rewards
    raw_tps = parse_promql_get_value(execute_promql_query(
      'sum(rate(nginx_http_requests_total[35s]))',
      query_timestamp
    ))

    raw_tps_success = parse_promql_get_value(execute_promql_query(
      'sum(rate(nginx_http_requests_total{status=~"2.*"}[35s]))/sum(rate(nginx_http_requests_total[35s]))',
      query_timestamp
    ))

    raw_request_latency = parse_promql_get_value(execute_promql_query(
      'rate(nginx_http_request_duration_seconds_sum[35s])',
      query_timestamp
    )) # note this is in seconds

    return JSONResponse(content = {
        'services': [
          [
            round(float(services_cpu[svc]), 5),
            round(float(services_mem[svc]), 5)
          ]
          for svc in ALL_SERVICES
        ],
        'tps': math.ceil(float(raw_tps)),
        'tps_success': math.ceil(float(raw_tps_success)),
        'latency_seconds': round(float(raw_request_latency), 3)
    })

@app.get('/service')
async def get_service_metrics(request: Request):
    global ALL_SERVICES
    return JSONResponse(content = {
        'services': ALL_SERVICES,
        'total_services': len(ALL_SERVICES)
    })
