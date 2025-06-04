from kubernetes import client, config
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from util import execute_promql_query, parse_promql_response_by_service, parse_promql_get_value

import logging
import math
import os
import time

TIME_OFFSET = 4
ALL_SERVICES = []
ALL_SERVICES_TYPE = []
CONTAINER_NAME_TO_SERVICE_IDX = {}

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S"
)

apps_v1 = None
v1 = None
k8s_api_client = None

# retrieve some resource data from Kubernetes before server initialises
@asynccontextmanager
async def lifespan(app: FastAPI):
  global ALL_SERVICES
  global ALL_SERVICES_TYPE
  global CONTAINER_NAME_TO_SERVICE_IDX
  global apps_v1, v1, k8s_api_client

  config.load_incluster_config()
  apps_v1 = client.AppsV1Api()
  v1 = client.CoreV1Api()
  k8s_api_client = client.ApiClient()

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
  yield

app = FastAPI(lifespan=lifespan)

@app.get('/service/metrics')
async def get_service_metrics(request: Request):
    global ALL_SERVICES
    query_timestamp = int(time.time() - TIME_OFFSET)

    # used to define state space
    services_cpu = parse_promql_response_by_service(execute_promql_query(
      'sum by (container) (rate(container_cpu_usage_seconds_total{namespace="default"}[1m])) / sum by (container) (kube_pod_container_resource_limits{namespace="default", resource="cpu"} + 1e-6)',
      query_timestamp
    ), default_value=0)

    services_mem = parse_promql_response_by_service(execute_promql_query(
      'sum by (container) (avg_over_time(container_memory_working_set_bytes{namespace="default"}[35s])) / sum by (container) (kube_pod_container_resource_limits{namespace="default", resource="memory"} + 1e-6)',
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

    request_latency_p95 = parse_promql_get_value(execute_promql_query(
      'sum(histogram_quantile(0.95, rate(nginx_http_request_duration_seconds_bucket[35s])))',
      query_timestamp
    ), default_value=0)

    request_latency_p99 = parse_promql_get_value(execute_promql_query(
      'sum(histogram_quantile(0.99, rate(nginx_http_request_duration_seconds_bucket[35s])))',
      query_timestamp
    ), default_value=0)

    total_replicas = parse_promql_response_by_service(execute_promql_query(
      'kube_deployment_spec_replicas{namespace="default"}',
      query_timestamp
    ), default_value=0, prom_label='deployment')

    global_cpu_util = parse_promql_get_value(execute_promql_query(
      'sum (rate(container_cpu_usage_seconds_total{namespace="default"}[45s])) / sum (machine_cpu_cores + 1e-6)',
      query_timestamp
    ), default_value=0)

    global_mem_util = parse_promql_get_value(execute_promql_query(
      'sum (rate(container_memory_usage_bytes{namespace="default"}[45s])) / sum (machine_memory_bytes + 1e-6)',
      query_timestamp
    ), default_value=0)

    return JSONResponse(content = {
        'services': {svc:
          [
            round(float(services_cpu.get(svc, 0)), 5),
            round(float(services_mem.get(svc, 0)), 5),
            int(total_replicas.get(svc, 1)),
          ]
          for svc in ALL_SERVICES
        },
        'tps': math.ceil(float(raw_tps)),
        'tps_success': math.ceil(float(raw_tps_success)),
        'latency_p95': round(float(request_latency_p95), 3),
        'latency_p99': round(float(request_latency_p99), 3),
        'global_cpu_util': round(float(global_cpu_util), 4),
        'global_mem_util': round(float(global_mem_util), 4),
    })

@app.get('/service')
async def get_service_metrics(request: Request):
    global ALL_SERVICES
    return JSONResponse(content = {
        'services': ALL_SERVICES,
        'total_services': len(ALL_SERVICES),
    })


@app.post("/scale/horizontal")
async def scale_deployment_horizontal(req: Request):
    global apps_v1
    req_body = await req.json()

    print(req_body)

    deploy_config = apps_v1.read_namespaced_deployment(name=req_body['deploy_name'], namespace='default')
    deploy_config.spec.replicas = req_body['replicas']
    apps_v1.patch_namespaced_deployment(name=req_body['deploy_name'], namespace='default', body=deploy_config)
    
    resp = {'success': True, 'new_replicas': deploy_config.spec.replicas}
    print(resp)
    return resp


@app.post("/scale/vertical")
async def scale_deployment_vertical(req: Request):
    global v1, k8s_api_client

    req_body = await req.json()
    deploy_name = req_body['deploy_name']

    print(req_body)

    # update resource limits for deployment which is associated with service pod label
    pods = v1.list_namespaced_pod(namespace='default', label_selector=f"service={deploy_name}")
    for pod in pods.items:
        new_resources = {
          'cpu': req_body.get('cpu', pod.spec.containers[0].resources.limits['cpu']),
          'memory': req_body.get('memory', pod.spec.containers[0].resources.limits['memory']),
        }

        # we assume pods do not need to restart based on resizePolicy: https://kubernetes.io/docs/tasks/configure-pod-container/resize-container-resources/
        patched_payload = {
            'spec': {
                'containers': [
                    {
                        'name': pod.spec.containers[0].name,
                        'resources': {
                            'requests': new_resources,
                            'limits': new_resources,
                        }
                    }
                ]
            }
        }

        k8s_api_client.call_api(
          f"/api/v1/namespaces/default/pods/{pod.metadata.name}/resize",
          'PATCH',
          body=patched_payload,
          header_params={"Content-Type": "application/merge-patch+json"},
          response_type="V1Pod",
          auth_settings = ['BearerToken'],
          _preload_content=False
        ) # for auth: https://stackoverflow.com/a/63747147

    resp = {'success': True, 'patch': patched_payload}
    print(resp)
    return resp



# def reset_env():
#     # set amount of pods per service to 1
#     for deploy in apps_v1.list_namespaced_deployment(namespace='default').items:
#       apps_v1.patch_namespaced_deployment_scale(
#           name=deploy.metadata.name,
#           namespace='default',
#           body={"spec": {"replicas": 1}}
#       )

