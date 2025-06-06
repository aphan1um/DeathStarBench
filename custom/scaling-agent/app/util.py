import os
import requests
import logging

PROMETHEUS_HOSTNAME = os.getenv('PROMETHEUS_HOSTNAME')

def execute_promql_query(query, time):
  response = requests.get(
    f'http://{PROMETHEUS_HOSTNAME}/api/v1/query',
    params={'query': query, 'time': time}
  )

  response_json = response.json()

  if response_json['status'] != 'success':
    logging.error(f'Query has failed: {query}')
    return default_value

  return response_json['data']


def parse_promql_response_by_service(data, default_value=None, prom_label="container"):
  if not isinstance(data, dict):
    return None

  result = data['result']
  return {item['metric'][prom_label]: item['value'][1] for item in result}


def parse_promql_get_value(data, default_value=None):
  if not isinstance(data, dict):
    return None

  return data['result'][0]['value'][1]
