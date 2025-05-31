#!/bin/bash

# parse each csv file representing workload traces from Alibaba's Microservice Traces 2021 experiment:
# https://github.com/alibaba/clusterdata/tree/master/cluster-trace-microservices-v2021
for i in $(seq 0 24); do
  echo "Handling MSRTQps_$i.tar.gz"
  tar -xzf "MSRTQps_$i.tar.gz"
  grep -Ei 'consumerMQ_MCR'  MSRTQps_$i.csv > MSRTQps_$i.csv.filtered
  awk -F, -v OFS=, '(NR>1) { rps[$3][$2] += $6;  } END { for (ms in rps) for (sec in rps[ms]) { print substr(ms, 0, 12), sec/(1000*60), rps[ms][sec] } }' MSRTQps_$i.csv.filtered > MSRTQps_$i.csv.parsed
  rm -f MSRTQps_$i.csv
done
