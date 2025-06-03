#!/usr/bin/env bash

date > start_time.txt

locust -f locust.py --headless --csv loadtest --csv-full-history --processes=6

date > end_time.txt
