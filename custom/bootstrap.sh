#!/usr/bin/env bash

# setup autoscaler admission webhook
kubectl apply -f scaler-ns.yaml
kubectl apply -f admin-rbac.yaml
kubectl apply -f k8s-scaler/spec.yaml

# create configmap storing current cpu and memory limits of microservices (scaler k8s namespace created in last step already)
DEPLOY_JSON="$(kubectl get deploy -o json)"
CPU_CONFIGMAP_DATA=$(echo "$DEPLOY_JSON" | \
  jq -r '.items | map("--from-literal=" + .metadata.name + "=" + .spec.template.spec.containers[0].resources.limits.cpu) | join(" ")'
)
MEM_CONFIGMAP_DATA=$(echo "$DEPLOY_JSON" | \
  jq -r '.items | map("--from-literal=" + .metadata.name + "=" + .spec.template.spec.containers[0].resources.limits.memory) | join(" ")'
)

set -x
kubectl -n scaler delete configmap cpu-limits mem-limits || true
kubectl -n scaler create configmap cpu-limits $CPU_CONFIGMAP_DATA
kubectl -n scaler create configmap mem-limits $MEM_CONFIGMAP_DATA

# install prometheus and grafana stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus \
  prometheus-community/kube-prometheus-stack \
  --create-namespace \
  --namespace monitor \
  --set alertmanager.enabled=false


# kube-prometheus-stack has been installed. Check its status by running:
#   kubectl --namespace monitor get pods -l "release=prometheus"

# Get Grafana 'admin' user password by running:

#   kubectl --namespace monitor get secrets prometheus-grafana -o jsonpath="{.data.admin-password}" | base64 -d ; echo

# Access Grafana local instance:

# export POD_NAME=$(kubectl --namespace monitor get pod -l "app.kubernetes.io/name=grafana,app.kubernetes.io/instance=prometheus" -oname)
# kubectl --namespace monitor port-forward $POD_NAME 3000

# export POD_NAME=$(kubectl --namespace monitor get pod -l "app.kubernetes.io/name=prometheus,app.kubernetes.io/instance=prometheus-kube-prometheus-prometheus" -oname)
# kubectl --namespace monitor port-forward $POD_NAME 9090
