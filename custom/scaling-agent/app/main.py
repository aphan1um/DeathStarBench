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
ALL_SERVICES = []
ALL_SERVICES_TYPE = []
CONTAINER_NAME_TO_SERVICE_IDX = {}

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
  global ALL_SERVICES_TYPE
  global CONTAINER_NAME_TO_SERVICE_IDX

  config.load_incluster_config()
  apps_v1 = client.AppsV1Api()

  # check and filter deployment or statefulset has 'service' label defined for pods created by them
  # we will use these as being eligible for horizontal scaling at the container level
  def has_valid_selector_label(k8s_object):
    return 'service' in k8s_object.spec.template.metadata.labels and k8s_object.spec.template.metadata.labels['service'] == k8s_object.metadata.name

  all_services = apps_v1.list_namespaced_deployment(namespace='default').items
  all_services = all_services + apps_v1.list_namespaced_stateful_set(namespace='default').items
  all_services = sorted([svc for svc in all_services if has_valid_selector_label(svc)], key=lambda s: s.metadata.name)

  for idx, svc in enumerate(all_services):
    # observe 1st container in pod only
    container_name = svc.spec.template.spec.containers[0].name
    if container_name in CONTAINER_NAME_TO_SERVICE_IDX:
      raise Exception('Found duplicate container name from a service')
    CONTAINER_NAME_TO_SERVICE_IDX[container_name] = idx

  # combine
  ALL_SERVICES = [d.metadata.name for d in all_services]
  ALL_SERVICES_TYPE = [d.kind for d in all_services]

  logging.info('Obtained services: [' + ','.join(ALL_SERVICES) + ']')
  logging.info('Maximum amount of pods per service: ' + str(ALL_SERVICES_MAX_REPLICAS))

  yield

app = FastAPI(lifespan=lifespan)

@app.get('/service/metrics')
async def get_service_metrics(request: Request):
    global ALL_SERVICES
    query_timestamp = int(time.time() - TIME_OFFSET)

    # used to define state space
    services_cpu = parse_promql_response_by_service(execute_promql_query(
      'sum by (container) (rate(container_cpu_usage_seconds_total{namespace="default"}[1m])) / sum by (container) (kube_pod_container_resource_requests{namespace="default", resource="cpu"} + 1e-6)',
      query_timestamp
    ), default_value=0)

    # cov = coefficient of variation
    services_cpu_cov = parse_promql_response_by_service(execute_promql_query(
      'stddev by (container) (rate(container_cpu_usage_seconds_total{namespace="default"}[1m])) / (avg by (container) (rate(container_cpu_usage_seconds_total{namespace="default"}[1m])) + 1e-5)',
      query_timestamp
    ), default_value=0)

    services_mem = parse_promql_response_by_service(execute_promql_query(
      'sum by (container) (avg_over_time(container_memory_working_set_bytes{namespace="default"}[35s])) / sum by (container) (kube_pod_container_resource_requests{namespace="default", resource="memory"} + 1e-6)',
      query_timestamp
    ), default_value={})

    services_mem_cov = parse_promql_response_by_service(execute_promql_query(
      'stddev by (container) (avg_over_time(container_memory_working_set_bytes{namespace="default"}[35s])) / avg by (container) (kube_pod_container_resource_requests{namespace="default", resource="memory"} + 1e-6)',
      query_timestamp
    ), default_value=0)

    # to be also used calculate rewards
    raw_tps = parse_promql_get_value(execute_promql_query(
      'sum(rate(nginx_http_requests_total[35s]))',
      query_timestamp
    ), default_value=0)

    raw_tps_success = parse_promql_get_value(execute_promql_query(
      'sum(rate(nginx_http_requests_total{status=~"2.*"}[35s]))',
      query_timestamp
    ), default_value=1) # this is a ratio (1 being the best value)

    raw_request_latency = parse_promql_get_value(execute_promql_query(
      'rate(nginx_http_request_duration_seconds_sum[35s])',
      query_timestamp
    ), default_value=0) # note this is in seconds

    return JSONResponse(content = {
        'services': [
          [
            round(float(services_cpu.get(svc, 0)), 5), round(float(services_cpu_cov.get(svc, 0)), 4),
            round(float(services_mem.get(svc, 0)), 5), round(float(services_mem_cov.get(svc, 0)), 4),
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
        'total_services': len(ALL_SERVICES),
        'max_replicas': ALL_SERVICES_MAX_REPLICAS
    })
