/**
 * k6 load test: cursor-based vs offset pagination comparison.
 *
 * Runs two scenarios in parallel:
 *   - offset_pagination: classic skip/limit — cost grows with skip depth
 *   - cursor_pagination: opaque cursor — O(1) cost at any depth
 *
 * Usage:
 *   k6 run scripts/testing/load_test_pagination.js
 *   k6 run --vus 20 --duration 60s scripts/testing/load_test_pagination.js
 *
 * Environment overrides:
 *   BASE_URL   - default: http://localhost:8000
 *   VUS        - virtual users per scenario (default: 10)
 *   DURATION   - test duration (default: 30s)
 *   LIMIT      - page size (default: 50)
 *
 * Prerequisites:
 *   - App running:  docker compose up app
 *   - Data seeded:  uv run python scripts/testing/seed_data.py 10000
 *   - k6 installed: https://k6.io/docs/get-started/installation/
 *                   brew install k6  |  snap install k6  |  choco install k6
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// ---------------------------------------------------------------------------
// Custom per-strategy metrics
// ---------------------------------------------------------------------------
const offsetDuration = new Trend("offset_req_duration", true); // true = high-res ms
const cursorDuration = new Trend("cursor_req_duration", true);
const offsetErrors = new Rate("offset_error_rate");
const cursorErrors = new Rate("cursor_error_rate");

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const LIMIT = parseInt(__ENV.LIMIT || "50");
const VUS = parseInt(__ENV.VUS || "10");
const DURATION = __ENV.DURATION || "30s";

// Offset pages to test: mix shallow (fast) and deep (slow) to show the
// full-table-scan cost degradation.
const OFFSET_PAGES = [0, 50, 200, 500, 1_000, 2_500, 5_000, 9_000];

export const options = {
  scenarios: {
    // -----------------------------------------------------------------------
    // Scenario A: classic offset/limit pagination
    // -----------------------------------------------------------------------
    offset_pagination: {
      executor: "constant-vus",
      vus: VUS,
      duration: DURATION,
      exec: "offsetScenario",
      tags: { strategy: "offset" },
    },

    // -----------------------------------------------------------------------
    // Scenario B: cursor-based pagination
    // -----------------------------------------------------------------------
    cursor_pagination: {
      executor: "constant-vus",
      vus: VUS,
      duration: DURATION,
      exec: "cursorScenario",
      tags: { strategy: "cursor" },
    },
  },

  thresholds: {
    // Cursor deep pages significantly faster than offset deep pages
    "offset_req_duration{depth:deep}": ["p(95)<1000"],
    "cursor_req_duration{depth:deep}": ["p(95)<300"],
    // Overall error rate must be low
    offset_error_rate: ["rate<0.01"],
    cursor_error_rate: ["rate<0.01"],
  },
};

// ---------------------------------------------------------------------------
// Scenario A — offset
// ---------------------------------------------------------------------------
export function offsetScenario() {
  for (const skip of OFFSET_PAGES) {
    const depth = skip >= 1_000 ? "deep" : "shallow";
    const res = http.get(`${BASE_URL}/api/v1/records?skip=${skip}&limit=${LIMIT}`, {
      tags: { strategy: "offset", depth },
    });

    const ok = check(res, {
      "offset 200": (r) => r.status === 200,
      "offset has items": (r) => {
        try {
          return Array.isArray(r.json());
        } catch {
          return false;
        }
      },
    });

    offsetErrors.add(!ok);
    offsetDuration.add(res.timings.duration, { depth });
    sleep(0.05);
  }
}

// ---------------------------------------------------------------------------
// Scenario B — cursor
// ---------------------------------------------------------------------------
export function cursorScenario() {
  let cursor = null;
  let page = 0;

  // Walk up to 30 pages per VU iteration — simulates deep traversal.
  for (let i = 0; i < 30; i++) {
    const depth = page >= 10 ? "deep" : "shallow";
    const qs = cursor ? `cursor=${cursor}&limit=${LIMIT}` : `limit=${LIMIT}`;
    const res = http.get(`${BASE_URL}/api/v2/records/cursor?${qs}`, {
      tags: { strategy: "cursor", depth },
    });

    const ok = check(res, {
      "cursor 200": (r) => r.status === 200,
      "cursor has records": (r) => {
        try {
          return Array.isArray(r.json().records);
        } catch {
          return false;
        }
      },
    });

    cursorErrors.add(!ok);
    cursorDuration.add(res.timings.duration, { depth });

    if (!ok) {
      cursor = null;
      page = 0;
      break;
    }

    const body = res.json();
    if (!body.has_more || !body.next_cursor) {
      // End of result set — reset chain so the VU starts over.
      cursor = null;
      page = 0;
      break;
    }

    cursor = body.next_cursor;
    page++;
    sleep(0.05);
  }
}

// ---------------------------------------------------------------------------
// Summary — printed after the test run
// ---------------------------------------------------------------------------
export function handleSummary(data) {
  const fmt = (v) => (v === undefined ? "   n/a   " : `${v.toFixed(1).padStart(7)}ms`);
  const fmtRate = (v) => (v === undefined ? "  n/a  " : `${(v * 100).toFixed(2).padStart(5)}%`);

  const om = (key) => data.metrics?.offset_req_duration?.values?.[key];
  const cm = (key) => data.metrics?.cursor_req_duration?.values?.[key];
  const oe = data.metrics?.offset_error_rate?.values?.rate;
  const ce = data.metrics?.cursor_error_rate?.values?.rate;

  const lines = [
    "",
    "╔════════════════════════════════════════════════════════════╗",
    "║          PAGINATION LOAD TEST SUMMARY                      ║",
    "╠════════════════════════════════════════════════════════════╣",
    "║ Strategy   │    p50     │    p95     │    p99     │ errors  ║",
    "╠════════════════════════════════════════════════════════════╣",
    `║ Offset     │ ${fmt(om("p(50)"))} │ ${fmt(om("p(95)"))} │ ${fmt(om("p(99)"))} │ ${fmtRate(oe)}  ║`,
    `║ Cursor     │ ${fmt(cm("p(50)"))} │ ${fmt(cm("p(95)"))} │ ${fmt(cm("p(99)"))} │ ${fmtRate(ce)}  ║`,
    "╚════════════════════════════════════════════════════════════╝",
    "",
    "Tip: deep-page offset cost grows with O(skip) — cursor stays O(1).",
    "",
  ].join("\n");

  console.log(lines);
  return { stdout: lines };
}
