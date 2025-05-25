from kubernetes import client, config
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import base64
import json

app = FastAPI()
config.load_incluster_config()

k8s_v1 = client.CoreV1Api()

@app.post('/mutate/pod-limits')
async def set_pod_limits_creation(request: Request):
    content = request.get_json()
    pod = content['request']['object']
    container = pod['spec']['containers'][0]
    deployment_name = pod['metadata']['labels']['app']

    cpu = k8s_v1.read_namespaced_config_map(name='cpu-limits', namespace='scaler').data[deployment_name]
    mem = k8s_v1.read_namespaced_config_map(name='mem-limits', namespace='scaler').data[deployment_name]

    new_limits = [
        {'op': 'add', 'path': '/spec/containers/0/resources/limits/memory', 'value': cpu},
        {'op': 'add', 'path': '/spec/containers/0/resources/limits/cpu', 'value': mem}
    ]

    # https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers
    return JSONResponse(content = {
        'response': {
            'uid': content['request']['id'],
            'allowed': True,
            'patchType': 'JSONPatch',
            'patch': base64.b64encode(json.dumps(new_limits).encode()).decode()
        }
    })
