{{- define "socialnetwork.templates.nginx.nginx.conf"  }}
# Load the OpenTracing dynamic module.
load_module modules/ngx_http_opentracing_module.so;

# Checklist: Make sure that worker_processes == #cores you gave to
# nginx process
worker_processes  auto;

# error_log  logs/error.log;

# Checklist: Make sure that worker_connections * worker_processes
# is greater than the total connections between the client and Nginx. 
events {
  use epoll;
  worker_connections  1024;
}

env fqdn_suffix;

http {
  # Load a vendor tracer
  opentracing on;
  opentracing_load_tracer /usr/local/lib/libjaegertracing_plugin.so /usr/local/openresty/nginx/jaeger-config.json;

  include       mime.types;
  default_type  application/octet-stream;

  proxy_read_timeout 5000;
  proxy_connect_timeout 5000;
  proxy_send_timeout 5000;
  
  log_format main '$remote_addr - $remote_user [$time_local] "$request"'
                  '$status $body_bytes_sent "$http_referer" '
                  '"$http_user_agent" "$http_x_forwarded_for"';
  # access_log  /dev/stdout  main;

  sendfile        on;
  tcp_nopush      on;
  tcp_nodelay     on;

  # Checklist: Make sure the keepalive_timeout is greateer than
  # the duration of your experiment and keepalive_requests
  # is greateer than the total number of requests sent from
  # the workload generator
  keepalive_timeout  120s;
  keepalive_requests 100000;

  # Docker default hostname resolver. Set valid timeout to prevent unlimited
  # ttl for resolver caching.
  # resolver 127.0.0.11 valid=10s ipv6=off;
  resolver {{ .Values.global.nginx.resolverName }} valid=10s ipv6=off;

  lua_package_path '/usr/local/openresty/nginx/lua-scripts/?.lua;/usr/local/openresty/luajit/share/lua/5.1/?.lua;;';

  lua_shared_dict config 32k;

  init_by_lua_block {
    local bridge_tracer = require "opentracing_bridge_tracer"
    local GenericObjectPool = require "GenericObjectPool"
    local ngx = ngx
    local jwt = require "resty.jwt"
    local cjson = require 'cjson'

    local social_network_UserTimelineService = require 'social_network_UserTimelineService'
    local UserTimelineServiceClient = social_network_UserTimelineService.social_network_UserTimelineService
    local social_network_SocialGraphService = require 'social_network_SocialGraphService'
    local SocialGraphServiceClient = social_network_SocialGraphService.SocialGraphServiceClient
    local social_network_ComposePostService = require 'social_network_ComposePostService'
    local ComposePostServiceClient = social_network_ComposePostService.ComposePostServiceClient
    local social_network_UserService = require 'social_network_UserService'
    local UserServiceClient = social_network_UserService.UserServiceClient


    local config = ngx.shared.config;
    config:set("secret", "secret")
    config:set("cookie_ttl", 3600 * 24)
    config:set("ssl", false)
  }

  # CUSTOM CODE: Add Prometheus data collection (source code: https://github.com/knyar/nginx-lua-prometheus)
  lua_shared_dict prometheus_metrics 8M;
  init_worker_by_lua_block {
      prometheus = require("prometheus").init("prometheus_metrics")
      metric_requests = prometheus:counter("nginx_http_requests_total", "Number of HTTP requests", {"host", "status"})
      metric_latency = prometheus:histogram(
        "nginx_http_request_duration_seconds",
        "HTTP request latency",
        {"host"},
        {0.01, 0.025, 0.05, 0.075, 0.1, 0.2, 0.3, 0.4, 0.5, 1, 1.5, 2, 4, 6, 8, 10, 15}
      )
  }

  log_by_lua_block {
    metric_requests:inc(1, {ngx.var.server_name, ngx.var.status})
    metric_latency:observe(tonumber(ngx.var.request_time), {ngx.var.server_name})
  }
  # END OF CUSTOM CODE

  server {

    # Checklist: Set up the port that nginx listens to.
    listen       8080 reuseport;
    server_name  localhost;

    # Checklist: Turn of the access_log and error_log if you
    # don't need them.
    access_log  off;
    # error_log off;

    lua_need_request_body on;

    # Used when SSL enabled
    lua_ssl_trusted_certificate /keys/CA.pem;
    lua_ssl_ciphers ALL:!ADH:!LOW:!EXP:!MD5:@STRENGTH;

    # CUSTOM CODE: Expose so Prometheus can pull traffic-related metrics
    location /metrics {
        content_by_lua_block {
            prometheus:collect()
        }
    }
    # END OF CUSTOM CODE


    # Checklist: Make sure that the location here is consistent
    # with the location you specified in wrk2.
    location /api/user/register {
          if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
          }
          if ($request_method = 'POST') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
          if ($request_method = 'GET') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
      content_by_lua '
          local client = require "api/user/register"
          client.RegisterUser();
      ';
    }

    location /api/user/follow {
          if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
          }
          if ($request_method = 'POST') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
          if ($request_method = 'GET') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
      content_by_lua '
          local client = require "api/user/follow"
          client.Follow();
      ';
    }

    location /api/user/unfollow {
          if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
          }
          if ($request_method = 'POST') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
          if ($request_method = 'GET') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
      content_by_lua '
          local client = require "api/user/unfollow"
          client.Unfollow();
      ';
    }

    location /api/user/login {
          if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
          }
          if ($request_method = 'POST') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
          if ($request_method = 'GET') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
      content_by_lua '
          local client = require "api/user/login"
          client.Login();
      ';
    }

    location /api/post/compose {
          if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
          }
          if ($request_method = 'POST') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
          if ($request_method = 'GET') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
      content_by_lua '
          local client = require "api/post/compose"
          client.ComposePost();
      ';
    }

    location /api/user-timeline/read {
          if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
          }
          if ($request_method = 'POST') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
          if ($request_method = 'GET') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
      content_by_lua '
          local client = require "api/user-timeline/read"
          client.ReadUserTimeline();
      ';
    }

    location /api/home-timeline/read {
            if ($request_method = 'OPTIONS') {
              add_header 'Access-Control-Allow-Origin' '*';
              add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
              add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
              add_header 'Access-Control-Max-Age' 1728000;
              add_header 'Content-Type' 'text/plain; charset=utf-8';
              add_header 'Content-Length' 0;
              return 204;
            }
            if ($request_method = 'POST') {
              add_header 'Access-Control-Allow-Origin' '*';
              add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
              add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
              add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
            }
            if ($request_method = 'GET') {
              add_header 'Access-Control-Allow-Origin' '*';
              add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
              add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
              add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
            }
      content_by_lua '
          local client = require "api/home-timeline/read"
          client.ReadHomeTimeline();
      ';
    }

    # # get userinfo lua
    # location /api/user/user_info {
    #       if ($request_method = 'OPTIONS') {
    #         add_header 'Access-Control-Allow-Origin' '*';
    #         add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
    #         add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
    #         add_header 'Access-Control-Max-Age' 1728000;
    #         add_header 'Content-Type' 'text/plain; charset=utf-8';
    #         add_header 'Content-Length' 0;
    #         return 204;
    #       }
    #       if ($request_method = 'POST') {
    #         add_header 'Access-Control-Allow-Origin' '*';
    #         add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
    #         add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
    #         add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
    #       }
    #       if ($request_method = 'GET') {
    #         add_header 'Access-Control-Allow-Origin' '*';
    #         add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
    #         add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
    #         add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
    #       }
    #   content_by_lua '
    #       local client = require "api/user/user_info"
    #       client.UserInfo();
    #   ';
    # }
    # get follower lua
    location /api/user/get_follower {
          if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
          }
          if ($request_method = 'POST') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
          if ($request_method = 'GET') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
      content_by_lua '
          local client = require "api/user/get_follower"
          client.GetFollower();
      ';
    }

    # get followee lua
    location /api/user/get_followee {
          if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
          }
          if ($request_method = 'POST') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
          if ($request_method = 'GET') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
          }
      content_by_lua '
          local client = require "api/user/get_followee"
          client.GetFollowee();
      ';
    }
    location / {
      if ($request_method = 'OPTIONS') {
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
        add_header 'Access-Control-Max-Age' 1728000;
        add_header 'Content-Type' 'text/plain; charset=utf-8';
        add_header 'Content-Length' 0;
        return 204;
      }
      if ($request_method = 'POST') {
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
        add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
      }
      if ($request_method = 'GET') {
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range';
        add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range';
      }
      root pages;
    }

    location /wrk2-api/home-timeline/read {
      content_by_lua '
          local client = require "wrk2-api/home-timeline/read"
          client.ReadHomeTimeline();
      ';
    }

    location /wrk2-api/user-timeline/read {
      content_by_lua '
          local client = require "wrk2-api/user-timeline/read"
          client.ReadUserTimeline();
      ';
    }

    location /wrk2-api/post/compose {
      content_by_lua '
          local client = require "wrk2-api/post/compose"
          client.ComposePost();
      ';
    }

    location /wrk2-api/user/register {
      content_by_lua '
          local client = require "wrk2-api/user/register"
          client.RegisterUser();
      ';
    }

    location /wrk2-api/user/follow {
      content_by_lua '
          local client = require "wrk2-api/user/follow"
          client.Follow();
      ';
    }

    location /wrk2-api/user/unfollow {
      content_by_lua '
          local client = require "wrk2-api/user/unfollow"
          client.Unfollow();
      ';
    }

  }
}
{{- end }}
