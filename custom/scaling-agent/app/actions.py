
k8s_v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()

# limits = {'cpu': <some value or does not exist>, 'mem': <some value or does not exist>}
def set_new_pod_resource_limits(service_name, limits, namespace='default'):
    deployment = apps_v1.read_namespaced_deployment(name=service_name, namespace=namespace)
    pod_labels = ','.join([f'{k}={v}' for k, v in deployment.spec.selector.match_labels])
    pods = core_v1.list_namespaced_pod(
        label_selector=','.join([f'{k}={v}' for k, v in deployment.spec.selector.match_labels]),
        namespace=namespace,
    )

    new_pod_limits = {}
    if 'cpu' in limits:
      new_pod_limits['cpu'] = limits['cpu']
    if 'memory' in limits:
      new_pod_limits['cpu'] = limits['memory']

    # https://kubernetes.io/docs/tasks/configure-pod-container/resize-container-resources/
    for p in pods:
        # only resize the first container, which is assumed to be the main application/service
        k8s_v1.patch_namespaced_pod_resize(
            name=p.metadata.name,
            namespace=namespace,
            body={
                'spec': {
                    'containers': [
                        'name': p.spec.containers.name[0],
                        'resources': {
                            'requests': new_pod_limits,
                            'limits': new_pod_limits,
                        }
                    ]
                }
            }
        )
