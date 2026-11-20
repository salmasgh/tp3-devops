"""Calcule les indicateurs RED d'un tir à partir des métriques eBPF de Beyla.

Usage : python scripts/red_stats.py <debut_epoch> <fin_epoch> [prometheus_url]

Les valeurs sont calculées sur toute la fenêtre du tir avec increase(),
puis histogram_quantile() pour les percentiles.
"""
import json
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

start, end = int(sys.argv[1]), int(sys.argv[2])
PROM = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:30090"
W = f"{end - start}s"
NS = 'namespace="perf-lab"'


def query(expr):
    url = f"{PROM}/api/v1/query?" + urllib.parse.urlencode({"query": expr, "time": end})
    res = json.load(urllib.request.urlopen(url))["data"]["result"]
    return float(res[0]["value"][1]) if res else float("nan")


def stats(metric, sel):
    s = f"{{{NS},{sel}}}"
    count = query(f"sum(increase({metric}_count{s}[{W}]))")
    errors = query(f'sum(increase({metric}_count{{{NS},{sel},http_response_status_code=~"5.."}}[{W}]))')
    total = query(f"sum(increase({metric}_sum{s}[{W}]))")
    row = {
        "requêtes": count,
        "RPS": count / (end - start),
        "moyenne_ms": 1000 * total / count if count else float("nan"),
    }
    for q in (0.5, 0.95, 0.99):
        row[f"p{int(q * 100)}_ms"] = 1000 * query(
            f"histogram_quantile({q}, sum(increase({metric}_bucket{s}[{W}])) by (le))")
    row["erreurs_%"] = 100 * (errors if errors == errors else 0) / count if count else float("nan")
    return row


rows = {
    "serveur order-api (A)": stats("http_server_request_duration_seconds", 'service_name="order-api"'),
    "client A -> B": stats("http_client_request_duration_seconds", 'service_name="order-api"'),
    "serveur pricing-engine (B)": stats("http_server_request_duration_seconds", 'service_name="pricing-engine"'),
}

cols = ["requêtes", "RPS", "moyenne_ms", "p50_ms", "p95_ms", "p99_ms", "erreurs_%"]
print(f"Fenêtre : {W}  (Prometheus {PROM})")
print(f"{'':28}" + "".join(f"{c:>12}" for c in cols))
for name, r in rows.items():
    print(f"{name:28}" + "".join(f"{r[c]:>12.1f}" for c in cols))

a, c = rows["serveur order-api (A)"], rows["client A -> B"]
print()
print("Décomposition (moyennes) : T_interne(A) = T_serveur(A) - T_client(A->B)")
print(f"  {a['moyenne_ms']:.2f} ms - {c['moyenne_ms']:.2f} ms = {a['moyenne_ms'] - c['moyenne_ms']:.2f} ms"
      f"  ({100 * (a['moyenne_ms'] - c['moyenne_ms']) / a['moyenne_ms']:.0f} % du temps de A)")
print("Décomposition (médianes) :")
print(f"  {a['p50_ms']:.2f} ms - {c['p50_ms']:.2f} ms = {a['p50_ms'] - c['p50_ms']:.2f} ms")
