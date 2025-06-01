from kubernetes import client, config
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import base64
import json
import logging

app = FastAPI()
config.load_incluster_config()

k8s_v1 = client.CoreV1Api()

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S"
)

# since modifying a deployment's specification forces to terminate old pods, we will set them to the right
# values prior to running the pod, as given by the RL agent and the config map
@app.post('/mutate/pod-limits')
async def set_pod_limits_creation(request: Request):
    content = await request.json()
    pod = content['request']['object']
    pod_name = pod['metadata']['name']
    container = pod['spec']['containers'][0]
    deployment_name = pod['metadata']['labels']['app']

    cpu = k8s_v1.read_namespaced_config_map(name='cpu-limits', namespace='scaler').data[deployment_name]
    mem = k8s_v1.read_namespaced_config_map(name='mem-limits', namespace='scaler').data[deployment_name]

    new_limits = [
        {'op': 'add', 'path': '/spec/containers/0/resources/limits/memory', 'value': cpu},
        {'op': 'add', 'path': '/spec/containers/0/resources/limits/cpu', 'value': mem}
    ]

    logging.info(f"[set_pod_limits_creation] Set limits for pod={pod_name} deploy={deployment_name}: cpu={cpu}, mem={mem}")

    # https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers
    return JSONResponse(content = {
        'response': {
            'uid': content['request']['uid'],
            'allowed': True,
            'patchType': 'JSONPatch',
            'patch': base64.b64encode(json.dumps(new_limits).encode()).decode()
        }
    })
