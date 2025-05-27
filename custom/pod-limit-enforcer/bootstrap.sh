#!/usr/bin/env bash

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
