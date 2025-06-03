from locust import HttpUser, task, events, LoadTestShape, FastHttpUser, constant_throughput
import math
import random
import string
import os
import numpy as np
from datetime import datetime

MAX_USER_INDEX = int(os.getenv("MAX_USER_INDEX", 962))
NODE_NGINX_ENDPOINT = [
  'http://10.44.112.4:30535',
  'http://10.44.112.5:30535',
  'http://10.44.112.6:30535',
  'http://10.44.112.7:30535',
  'http://10.44.112.8:30535',
]

WORKLOAD_RPS = "./test_70d6477dee4d.csv"

READ_TIMEOUT = 10

TOTAL_USERS_MULTIPLE = 1.5 # how many additional users as a multiple
LOAD_MULTIPLIER = 5 # defines how much additional load each user can delive

workload_rps_parsed = list(map(float, open(WORKLOAD_RPS).read().splitlines()))

print(f'Min load: {min(workload_rps_parsed)*LOAD_MULTIPLIER}')
print(f'Max load: {max(workload_rps_parsed)*LOAD_MULTIPLIER}')

def string_random(length):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def dec_random(length):
    return ''.join(random.choices(string.digits, k=length))


def random_node():
  return random.choice(NODE_NGINX_ENDPOINT)

class SocialNetworkUser(FastHttpUser):
    host = 'http://localhost:8080'
    wait_time = constant_throughput(LOAD_MULTIPLIER) # ~total users * LOAD_MULTIPLIER

    @task(40)
    def read_home_timeline(self):
        user_id = random.randint(0, MAX_USER_INDEX - 1)
        start = random.randint(0, 100)
        stop = start + 10

        hostname = random_node()
        path = "/wrk2-api/home-timeline/read"

        self.client.get(f"{hostname}{path}",
                        name=path,
                        params={"user_id": user_id, "start": start, "stop": stop},
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        timeout=READ_TIMEOUT)

    @task(60)
    def compose_post(self):
        user_index = random.randint(0, MAX_USER_INDEX - 1)
        username = f"username_{user_index}"
        user_id = str(user_index)
        text = string_random(256)

        num_media = random.randint(0, 4)
        num_user_mentions = random.randint(0, 5)
        num_urls = random.randint(0, 5)

        for _ in range(num_user_mentions):
            while True:
              mention_id = random.randint(0, MAX_USER_INDEX - 1)
              if mention_id != user_index:
                break
              text += f" @username_{mention_id}"


        for _ in range(num_urls):
            text += f" http://{string_random(64)}"

        media_ids = '[' + ','.join([f'"{dec_random(18)}"' for _ in range(num_media)]) + ']'
        media_types = '[' + ','.join(['"png"'] * num_media) + ']'

        data = {
            "username": username,
            "user_id": user_id,
            "text": text,
            "media_ids": media_ids,
            "media_types": media_types,
            "post_type": 0
        }

        hostname = random_node()
        path = "/wrk2-api/post/compose"

        self.client.post(f"{hostname}{path}",
                         name=path,
                         data=data,
                         headers={"Content-Type": "application/x-www-form-urlencoded"},
                         timeout=READ_TIMEOUT)


class StepLoadShape(LoadTestShape):
    total_time = 60 * len(workload_rps_parsed) # 12 hours
    time_interval = -1
    current_num_users = 100
    total_users_within_minute = []

    ramp_seconds = 2700 # amount of seconds before achieving peak load
    ramp_users = 5

    update_users_rate_seconds = 20 # should be divisible by 60

    def tick(self):
        if self.get_run_time() > self.total_time + 15:
            return None

        curr_second = int(self.get_run_time())

        if curr_second % self.update_users_rate_seconds == 0:
            new_time_interval = int(curr_second / 60)
            if new_time_interval > self.time_interval:
                workload_rps_new = workload_rps_parsed[min(self.time_interval, len(workload_rps_parsed))] * TOTAL_USERS_MULTIPLE
                self.time_interval = new_time_interval
                self.total_users_within_minute = np.random.poisson(workload_rps_new, int(60/self.update_users_rate_seconds))

            self.current_num_users = self.total_users_within_minute[curr_second % self.update_users_rate_seconds]
            self.ramp_users = random.randint(5, 16)

            if curr_second < self.ramp_seconds:
                self.current_num_users *= 0.05 + 0.95 * (curr_second / self.ramp_seconds)

        return (self.current_num_users, self.ramp_users)
