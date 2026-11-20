"""Génère dashboards/red-ebpf.json et le ConfigMap Grafana correspondant.

Toutes les requêtes portent sur les histogrammes produits par Beyla (eBPF).
"""
import json
import pathlib

DS = {"type": "prometheus", "uid": "prometheus"}
NS = 'namespace="perf-lab"'
SRV = "http_server_request_duration_seconds"
CLI = "http_client_request_duration_seconds"
A = 'service_name="order-api"'
B = 'service_name="pricing-engine"'

panels = []
pid = 0


def panel(title, targets, x, y, w, h, unit="short", kind="timeseries", desc="", extra=None):
    global pid
    pid += 1
    p = {
        "id": pid, "type": kind, "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [{"refId": chr(65 + i), "datasource": DS, "expr": e, "legendFormat": l}
                    for i, (e, l) in enumerate(targets)],
        "fieldConfig": {"defaults": {"unit": unit, "decimals": 1,
                                     "custom": {"lineWidth": 2, "fillOpacity": 8, "showPoints": "never"}},
                        "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "right",
                               "calcs": ["mean", "max", "lastNotNull"]},
                    "tooltip": {"mode": "multi"}},
    }
    if kind == "stat":
        p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value",
                        "graphMode": "area", "textMode": "value_and_name"}
        p["fieldConfig"]["defaults"].pop("custom")
    if extra:
        extra(p)
    panels.append(p)


def row(title, y):
    global pid
    pid += 1
    panels.append({"id": pid, "type": "row", "title": title, "collapsed": False,
                   "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []})


def q(quant, metric, sel):
    return f'histogram_quantile({quant}, sum(rate({metric}_bucket{{{NS},{sel}}}[1m])) by (le))'


def avg(metric, sel):
    return f'sum(rate({metric}_sum{{{NS},{sel}}}[1m])) / sum(rate({metric}_count{{{NS},{sel}}}[1m]))'


# ---- Synthèse : valeurs calculées sur toute la période affichée ($__range)
def inst(p):
    for t in p["targets"]:
        t["instant"] = True
        t["range"] = False


R = "$__range"
row("Synthèse sur la période affichée", 0)
panel("Débit max order-api", [(f'max_over_time(sum(rate({SRV}_count{{{NS},{A}}}[1m]))[{R}:15s])', "RPS max")], 0, 1, 4, 4, "reqps", "stat", extra=inst)
panel("Erreurs 5xx order-api", [(f'(sum(increase({SRV}_count{{{NS},{A},http_response_status_code=~"5.."}}[{R}])) or vector(0)) / sum(increase({SRV}_count{{{NS},{A}}}[{R}]))', "5xx")], 4, 1, 4, 4, "percentunit", "stat", extra=inst)
panel("Moyenne order-api", [(f'sum(increase({SRV}_sum{{{NS},{A}}}[{R}])) / sum(increase({SRV}_count{{{NS},{A}}}[{R}]))', "moyenne")], 8, 1, 4, 4, "s", "stat", extra=inst)
for i, qq in enumerate((0.5, 0.95, 0.99)):
    panel(f"p{int(qq*100)} order-api", [(f'histogram_quantile({qq}, sum(increase({SRV}_bucket{{{NS},{A}}}[{R}])) by (le))', f"p{int(qq*100)}")], 12 + 4 * i, 1, 4, 4, "s", "stat", extra=inst)

# ---- Rate
row("Rate : débit par service", 5)
panel("Débit entrant par service (requêtes serveur reçues)",
      [(f'sum(rate({SRV}_count{{{NS}}}[1m])) by (service_name)', "{{service_name}}")],
      0, 6, 12, 8, "reqps", desc="Requêtes reçues par order-api et par pricing-engine (sondes serveur eBPF).")
panel("Débit sortant order-api → pricing-engine (requêtes client)",
      [(f'sum(rate({CLI}_count{{{NS}}}[1m])) by (service_name, server_address)', "{{service_name}} → {{server_address}}")],
      12, 6, 12, 8, "reqps")

# ---- Errors
row("Errors : propagation des erreurs", 14)
panel("Taux d'erreurs 5xx par service (vue serveur)",
      [(f'(sum(rate({SRV}_count{{{NS},http_response_status_code=~"5.."}}[1m])) by (service_name) or sum(rate({SRV}_count{{{NS}}}[1m])) by (service_name) * 0) / sum(rate({SRV}_count{{{NS}}}[1m])) by (service_name)', "{{service_name}}"),
       (f'(sum(rate({CLI}_count{{{NS},http_response_status_code=~"5.."}}[1m])) by (service_name) or sum(rate({CLI}_count{{{NS}}}[1m])) by (service_name) * 0) / sum(rate({CLI}_count{{{NS}}}[1m])) by (service_name)', "client {{service_name}} → pricing-engine")],
      0, 15, 12, 8, "percentunit", extra=lambda p: p["fieldConfig"]["defaults"].update(min=0, max=0.2))
panel("Réponses par code HTTP (serveur et client)",
      [(f'sum(rate({SRV}_count{{{NS}}}[1m])) by (service_name, http_response_status_code)', "serveur {{service_name}} : {{http_response_status_code}}"),
       (f'sum(rate({CLI}_count{{{NS}}}[1m])) by (service_name, http_response_status_code)', "client {{service_name}} → B : {{http_response_status_code}}")],
      12, 15, 12, 8, "reqps")

# ---- Duration
row("Duration : percentiles de latence", 23)
panel("order-api : moyenne, p50, p95, p99",
      [(avg(SRV, A), "moyenne"), (q(0.5, SRV, A), "p50"), (q(0.95, SRV, A), "p95"), (q(0.99, SRV, A), "p99")],
      0, 24, 12, 9, "s")
panel("pricing-engine : moyenne, p50, p95, p99",
      [(avg(SRV, B), "moyenne"), (q(0.5, SRV, B), "p50"), (q(0.95, SRV, B), "p95"), (q(0.99, SRV, B), "p99")],
      12, 24, 12, 9, "s")

# ---- Décomposition
row("Décomposition de la latence : T_interne(A) = T_serveur(A) − T_client(A→B)", 33)
panel("Latence moyenne : serveur A, client A→B et temps interne de A",
      [(avg(SRV, A), "T_serveur(A)"), (avg(CLI, A), "T_client(A→B)"),
       (f'({avg(SRV, A)}) - ({avg(CLI, A)})', "T_interne(A)"), (avg(SRV, B), "T_serveur(B)")],
      0, 34, 12, 9, "s")
panel("Médiane (p50) : serveur A, client A→B et différence",
      [(q(0.5, SRV, A), "p50 T_serveur(A)"), (q(0.5, CLI, A), "p50 T_client(A→B)"),
       (f'({q(0.5, SRV, A)}) - ({q(0.5, CLI, A)})', "p50 T_serveur(A) − p50 T_client")],
      12, 34, 12, 9, "s")

# ---- Saturation
row("Saturation CPU de pricing-engine et loi de Little", 43)
panel("CPU pricing-engine (cœurs) et limite",
      [('sum(rate(container_cpu_usage_seconds_total{namespace="perf-lab",container="pricing-engine"}[1m]))', "CPU utilisé"),
       ('max(kube_pod_container_resource_limits{namespace="perf-lab",container="pricing-engine",resource="cpu"})', "limite CPU")],
      0, 44, 8, 8, "short", extra=lambda p: p["fieldConfig"]["defaults"].update(decimals=2, min=0))
panel("Throttling CFS pricing-engine (% périodes bridées)",
      [('sum(rate(container_cpu_cfs_throttled_periods_total{namespace="perf-lab",container="pricing-engine"}[1m])) / sum(rate(container_cpu_cfs_periods_total{namespace="perf-lab",container="pricing-engine"}[1m]))', "throttled")],
      8, 44, 8, 8, "percentunit", extra=lambda p: p["fieldConfig"]["defaults"].update(min=0, max=1))
panel("Requêtes en cours dans pricing-engine : L = λ × W (loi de Little)",
      [(f'sum(rate({SRV}_count{{{NS},{B}}}[1m])) * ({avg(SRV, B)})', "L = λ × W (pricing-engine)"),
       (f'sum(rate({SRV}_count{{{NS},{A}}}[1m])) * ({avg(SRV, A)})', "L = λ × W (order-api)")],
      16, 44, 8, 8, "short")

dashboard = {
    "uid": "tp3-red-ebpf", "title": "TP3 - RED eBPF (order-api → pricing-engine)",
    "tags": ["tp3", "ebpf", "beyla", "red"], "timezone": "browser", "schemaVersion": 39,
    "refresh": "10s", "time": {"from": "now-30m", "to": "now"}, "panels": panels,
}

root = pathlib.Path(__file__).resolve().parent
(root / "red-ebpf.json").write_text(json.dumps(dashboard, indent=2, ensure_ascii=False), encoding="utf-8")
cm = {
    "apiVersion": "v1", "kind": "ConfigMap",
    "metadata": {"name": "tp3-red-ebpf-dashboard", "namespace": "monitoring",
                 "labels": {"grafana_dashboard": "1"}},
    "data": {"red-ebpf.json": json.dumps(dashboard, ensure_ascii=False)},
}
(root / "grafana-dashboard-configmap.json").write_text(json.dumps(cm, indent=2, ensure_ascii=False), encoding="utf-8")
print("ok", len(panels), "panels")
