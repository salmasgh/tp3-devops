// Scénario de charge k6 sur POST /order (order-api).
//   PROFILE=constant : débit constant RATE req/s pendant DURATION (défaut 50 RPS, 3 min)
//   PROFILE=ramp     : montée par paliers de 25 à 150 RPS (saturation CPU)
import http from 'k6/http';
import { check } from 'k6';

const TARGET = __ENV.TARGET || 'http://order-api.perf-lab.svc.cluster.local:8000';
const RATE = Number(__ENV.RATE || 50);
const DURATION = __ENV.DURATION || '3m';
const PROFILE = __ENV.PROFILE || 'constant';

const profiles = {
  constant: {
    executor: 'constant-arrival-rate',
    rate: RATE,
    timeUnit: '1s',
    duration: DURATION,
    preAllocatedVUs: 50,
    maxVUs: 500,
  },
  ramp: {
    executor: 'ramping-arrival-rate',
    startRate: 25,
    timeUnit: '1s',
    preAllocatedVUs: 100,
    // Au plus 400 requêtes en vol : au-delà, k6 abandonne les itérations
    // (dropped_iterations) au lieu d'ouvrir des milliers de connexions.
    maxVUs: 400,
    stages: [
      { target: 25, duration: '1m' },
      { target: 50, duration: '15s' }, { target: 50, duration: '1m' },
      { target: 75, duration: '15s' }, { target: 75, duration: '1m' },
      { target: 100, duration: '15s' }, { target: 100, duration: '1m' },
      { target: 125, duration: '15s' }, { target: 125, duration: '1m' },
      { target: 150, duration: '15s' }, { target: 150, duration: '1m' },
    ],
  },
};

export const options = {
  scenarios: { orders: profiles[PROFILE] },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

const products = ['laptop', 'phone', 'headset', 'keyboard'];

export default function () {
  const payload = JSON.stringify({
    product: products[Math.floor(Math.random() * products.length)],
    quantity: 1 + Math.floor(Math.random() * 5),
    customer: `customer-${__VU}`,
  });
  const res = http.post(`${TARGET}/order`, payload, {
    headers: { 'Content-Type': 'application/json' },
    timeout: '30s',
  });
  check(res, { 'status is 201': (r) => r.status === 201 });
}
