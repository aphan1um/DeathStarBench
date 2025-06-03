import requests
import numpy as np
import gymnasium as gym
import time

class EnvSocialNetwork(gym.Env):
    def __init__(self, ip_address, expected_tps=100) -> None:
        self.status_url = f"http://{ip_address}:32500"

        # min is also the initial value set by all Kubernetes deployments
        self.MIN_CPU = 500
        self.MAX_CPU = 2000
        self.MIN_MEM = 500
        self.MAX_MEM = 1800
        self.MIN_REPLICAS = 1
        self.MAX_REPLICAS = 12

        # step increase if vertically scaling a pod's cpu or mem limits
        # (within max or min limits of course)
        self.STEP_CPU = 20
        self.SELF_MEM = 30

        self.SLO_LATENCY = 500
        self.EXPECTED_TPS = expected_tps

        self.ALL_SERVICES = [
          "compose-post-service",
          "home-timeline-redis",
          "home-timeline-service",
          "jaeger",
          "media-frontend",
          "media-memcached",
          "media-mongodb",
          "media-service",
          "nginx-thrift",
          "post-storage-memcached",
          "post-storage-mongodb",
          "post-storage-service",
          "social-graph-mongodb",
          "social-graph-redis",
          "social-graph-service",
          "text-service",
          "unique-id-service",
          "url-shorten-memcached",
          "url-shorten-mongodb",
          "url-shorten-service",
          "user-memcached",
          "user-mention-service",
          "user-mongodb",
          "user-service",
          "user-timeline-mongodb",
          "user-timeline-redis",
          "user-timeline-service"
        ]

        # number (0, 1) representing how important it is to utilise cpu and mem
        self.RESOURCE_UTIL_PRIO = 0.3

        # how many seconds until the environment is observed and action is taken by agent
        self.QUERY_WAIT_TIME = 18

        self.timestep = 0
        self.episode = 0

        # state space
        #   -> for a deployment = [cpu util, mem util, replica util (total pods / MAX_REPLICAS)]
        #   -> global           = [requests per second, p95 latency, global cpu util, global mem util]
        # self.observation_space = gym.spaces.Box(
        #     shape=(len(self.ALL_SERVICES) * 3 + 2,),
        #     dtype=int
        # )

        # actions = do nothing + inc/dec pods + inc/dec cpu or mem limits
        self.action_space = gym.spaces.Discrete(1 + len(self.ALL_SERVICES) * 6)


    def _get_obs(self):
      # get status of benchmark application
      response = requests.get(f"{self.status_url}/service/metrics")

      while response.status_code != 200:
        time.sleep(12)
        response = requests.get(f"{self.status_url}/service/metrics")

      response_body = response.json()

      obs_services = np.array([[
          response_body['services'][svc_stat][0],
          response_body['services'][svc_stat][1],
          response_body['services'][svc_stat][2]/self.MAX_REPLICAS
        ]
        for svc_stat in self.ALL_SERVICES
      ]).flatten()

      obs = np.append(obs_services, np.array([
        response_body['tps']/self.EXPECTED_TPS,
        response_body['latency_p95']/self.SLO_LATENCY,
        response_body['global_cpu_util'],
        response_body['global_mem_util']
      ]))

      return obs


    def _calculate_reward(self, obs):
      resource_util_score = (obs[-1] + obs[-2])/2.0
      request_rate_score = obs[-4]/self.EXPECTED_TPS
      
      # max value is 2
      return self.RESOURCE_UTIL_PRIO * resource_util_score + (1 - self.RESOURCE_UTIL_PRIO) * request_rate_score

    def reset(self):
      pass


    def step(self, action):
      done = False
      reward = 0
      next_obs = self._get_obs()
      info = None

      return next_obs, reward, done, False, info
