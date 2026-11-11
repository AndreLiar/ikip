// IKIP load test (Story 5.6 AC4) — k6.
//
//   BASE_URL=http://localhost:8000 TENANT_ID=<uuid> k6 run load/k6/ask_load.js
//   # Grafana Cloud k6 (cloud run): k6 cloud load/k6/ask_load.js
//
// NOTE: this is a committed, versioned ARTIFACT, run on demand — NOT a CI gate. A realistic
// load test needs a deployed, resource-sized target serving real traffic; IKIP has no cloud
// deployment yet (that is Epic 6). Until then this runs locally against a running API, or
// `k6 cloud` once a staging/prod URL exists. (A faked-dependency CI smoke run was considered
// and dropped: with Azure/DB faked away it only measures framework overhead — low value.)
//
// Ramps virtual users against /ask and enforces SLO thresholds (p95 latency, error rate).
// Auth: requests a dev token first (needs AUTH_DEV_LOGIN=true on the target API). The same
// run drives the OTel metrics the ops dashboard shows.
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const TENANT_ID = __ENV.TENANT_ID || "00000000-0000-4000-8000-000000000001";
const errors = new Rate("ask_errors");

export const options = {
  scenarios: {
    ramp: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "30s", target: 5 },
        { duration: "1m", target: 10 },
        { duration: "30s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<3000"], // p95 answer latency under 3s
    ask_errors: ["rate<0.01"], // under 1% errors
  },
};

function token() {
  const res = http.post(
    `${BASE_URL}/api/v1/auth/dev-token`,
    JSON.stringify({ tenant_id: TENANT_ID, role: "technician" }),
    { headers: { "Content-Type": "application/json" } },
  );
  return res.json("access_token");
}

export function setup() {
  return { token: token() };
}

const QUESTIONS = [
  "What does fault code E42 mean on pump P-12?",
  "What is the current recommended coolant for the CX-7 chiller?",
  "What grease grade applies to bearing B-204?",
  "What is the maximum operating pressure of vessel V-3?",
];

export default function (data) {
  const q = QUESTIONS[Math.floor(Math.random() * QUESTIONS.length)];
  const res = http.post(`${BASE_URL}/api/v1/ask`, JSON.stringify({ query: q }), {
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${data.token}` },
  });
  const ok = check(res, {
    "status 200": (r) => r.status === 200,
    "has status field": (r) => r.json("status") !== undefined,
  });
  errors.add(!ok);
  sleep(1);
}
