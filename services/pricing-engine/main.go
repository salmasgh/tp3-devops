// pricing-engine (Service B) : moteur de calcul tarifaire GET /price.
//
// Variables d'environnement d'injection de fautes :
//   BASE_LATENCY_MS  latence de base de chaque requête (défaut 10)
//   SLOW_RATIO       part des requêtes lentes, entre 0 et 1 (défaut 0)
//   SLOW_LATENCY_MS  latence des requêtes lentes (défaut 600)
//   ERROR_RATE       part des requêtes en HTTP 500, entre 0 et 1 (défaut 0)
//   CPU_WORK         itérations de calcul CPU par requête (défaut 0)
//
// Aucune bibliothèque d'observabilité : Beyla instrumente le binaire Go
// par uprobes sur net/http.
package main

import (
	"encoding/json"
	"log"
	"math"
	"math/rand"
	"net/http"
	"os"
	"strconv"
	"time"
)

var (
	baseLatency = envFloat("BASE_LATENCY_MS", 10)
	slowRatio   = envFloat("SLOW_RATIO", 0)
	slowLatency = envFloat("SLOW_LATENCY_MS", 600)
	errorRate   = envFloat("ERROR_RATE", 0)
	cpuWork     = int(envFloat("CPU_WORK", 0))
	catalog     = map[string]float64{"laptop": 1299.0, "phone": 799.0, "headset": 149.0, "keyboard": 89.0}
)

func envFloat(key string, def float64) float64 {
	if v, err := strconv.ParseFloat(os.Getenv(key), 64); err == nil {
		return v
	}
	return def
}

// burn consomme du CPU de façon déterministe (coût fixe par requête).
func burn(n int) float64 {
	x := 0.0
	for i := 0; i < n; i++ {
		x += math.Sqrt(float64(i))
	}
	return x
}

var sink float64

func price(w http.ResponseWriter, r *http.Request) {
	if cpuWork > 0 {
		sink += burn(cpuWork)
	}
	latency := baseLatency
	if rand.Float64() < slowRatio {
		latency = slowLatency
	}
	time.Sleep(time.Duration(latency * float64(time.Millisecond)))

	w.Header().Set("Content-Type", "application/json")
	if rand.Float64() < errorRate {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": "pricing failure"})
		return
	}
	product := r.URL.Query().Get("product")
	qty, err := strconv.Atoi(r.URL.Query().Get("quantity"))
	if err != nil || qty < 1 {
		qty = 1
	}
	unit, ok := catalog[product]
	if !ok {
		unit = 49.9
	}
	json.NewEncoder(w).Encode(map[string]any{
		"product":    product,
		"quantity":   qty,
		"unit_price": unit,
		"total":      math.Round(unit*float64(qty)*100) / 100,
		"currency":   "EUR",
	})
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /price", price)
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	log.Printf("pricing-engine listening on :8080 (base=%vms slow=%v@%vms err=%v cpu=%d)",
		baseLatency, slowRatio, slowLatency, errorRate, cpuWork)
	log.Fatal(http.ListenAndServe(":8080", mux))
}
