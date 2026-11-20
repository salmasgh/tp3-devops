"""Indicateurs par palier du tir en rampe (k6 PROFILE=ramp).

Usage : python scripts/saturation_steps.py <debut_epoch> [prometheus_url]
Chaque palier dure 1 min ; les mesures portent sur ses 45 dernières secondes.
"""
import json
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
start = int(sys.argv[1])
PROM = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:30090"
NS = 'namespace="perf-lab"'
# (débit demandé, fin du palier en secondes depuis le début du tir)
STEPS = [(25, 60), (50, 135), (75, 210), (100, 285), (125, 360), (150, 435)]


def q(expr, t):
    url = f"{PROM}/api/v1/query?" + urllib.parse.urlencode({"query": expr, "time": t})
    r = json.load(urllib.request.urlopen(url))["data"]["result"]
    return float(r[0]["value"][1]) if r else float("nan")


def srv(svc, what):
    return f'http_server_request_duration_seconds_{what}{{{NS},service_name="{svc}"}}'


print(f"{'demandé':>8} {'débit A':>8} {'débit B':>8} {'moy A':>8} {'p50 A':>8} {'p99 A':>8}"
      f" {'moy B':>8} {'A->B':>8} {'CPU B':>6} {'bridé':>6} {'L=λW':>6}")
print(f"{'req/s':>8} {'req/s':>8} {'req/s':>8} {'ms':>8} {'ms':>8} {'ms':>8} {'ms':>8} {'ms':>8}"
      f" {'cœur':>6} {'%':>6} {'req':>6}")
for rate, end in STEPS:
    t, w = start + end, "45s"
    ra = q(f"sum(rate({srv('order-api', 'count')}[{w}]))", t)
    rb = q(f"sum(rate({srv('pricing-engine', 'count')}[{w}]))", t)
    ma = q(f"sum(rate({srv('order-api', 'sum')}[{w}])) / sum(rate({srv('order-api', 'count')}[{w}]))", t)
    p50 = q(f"histogram_quantile(0.5, sum(rate({srv('order-api', 'bucket')}[{w}])) by (le))", t)
    p99 = q(f"histogram_quantile(0.99, sum(rate({srv('order-api', 'bucket')}[{w}])) by (le))", t)
    mb = q(f"sum(rate({srv('pricing-engine', 'sum')}[{w}])) / sum(rate({srv('pricing-engine', 'count')}[{w}]))", t)
    cli = 'http_client_request_duration_seconds_%s{' + NS + ',service_name="order-api"}'
    mc = q(f"sum(rate({cli % 'sum'}[{w}])) / sum(rate({cli % 'count'}[{w}]))", t)
    cpu = q(f'sum(rate(container_cpu_usage_seconds_total{{{NS},container="pricing-engine"}}[{w}]))', t)
    thr = q(f'sum(rate(container_cpu_cfs_throttled_periods_total{{{NS},container="pricing-engine"}}[{w}]))'
            f' / sum(rate(container_cpu_cfs_periods_total{{{NS},container="pricing-engine"}}[{w}]))', t)
    print(f"{rate:8d} {ra:8.1f} {rb:8.1f} {1000*ma:8.0f} {1000*p50:8.0f} {1000*p99:8.0f}"
          f" {1000*mb:8.0f} {1000*mc:8.0f} {cpu:6.3f} {100*thr:6.0f} {ra*ma:6.1f}")
