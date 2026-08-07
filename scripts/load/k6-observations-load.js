import http from 'k6/http';
import { check, fail, group, sleep } from 'k6';

const faultMode = __ENV.RESILIENCE_FAULT_MODE === 'inference-slow';

if (faultMode) {
  http.setResponseCallback(http.expectedStatuses(503));
}

export const options = faultMode ? {
  scenarios: {
    inference_bulkhead: {
      executor: 'per-vu-iterations',
      vus: 21,
      iterations: 1,
      maxDuration: '25s',
    },
  },
  thresholds: {
    checks: ['rate==1'],
    http_req_duration: ['p(99)<25000'],
    http_req_failed: ['rate==0'],
  },
} : {
  scenarios: {
    warmup: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 5 },
        { duration: '60s', target: 5 },
        { duration: '30s', target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.05'],
    group_duration: ['p(95)<600'],
  },
};

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const TOKEN = __ENV.BEARER_TOKEN;

if (!TOKEN) {
  fail('BEARER_TOKEN is required; create a local writer/admin token with `just smoke-token`.');
}

const headers = {
  'Content-Type': 'application/json',
  Authorization: `Bearer ${TOKEN}`,
};

export function setup() {
  return {};
}

export default function () {
  if (faultMode) {
    const response = http.get(`${BASE}/api/v1/vector-search/health`, { headers });
    check(response, {
      'inference fault returns 503': (r) => r.status === 503,
    });
    return;
  }

  group('health', () => {
    const health = http.get(`${BASE}/health`);
    check(health, {
      'health 200': (r) => r.status === 200,
    });
    sleep(0.5);
  });

  group('sources-read', () => {
    const sources = http.get(`${BASE}/api/v1/sources?limit=20`, {
      headers,
    });
    check(sources, {
      'sources 200': (r) => r.status === 200,
    });
    sleep(0.3);
  });

  group('observations-write', () => {
    const obs = {
      source: 'k6-load',
      data: { ts: Date.now(), vus: __VU, iter: __ITER },
      tags: ['load', 'k6'],
    };
    const created = http.post(
      `${BASE}/api/v1/observations`,
      JSON.stringify(obs),
      { headers },
    );
    check(created, {
      'obs 201': (r) => r.status === 201,
      'obs has id': (r) => r.json().id !== undefined,
    });
    sleep(0.2);
  });

  group('observations-read', () => {
    const list = http.get(`${BASE}/api/v1/observations?limit=10`, {
      headers,
    });
    check(list, {
      'list 200': (r) => r.status === 200,
      'has items': (r) => Array.isArray(r.json().observations),
    });
    sleep(0.2);
  });

  group('scorecards', () => {
    const scorecards = http.get(`${BASE}/api/v1/scorecards?limit=10`, {
      headers,
    });
    check(scorecards, {
      'scorecards 200': (r) => r.status === 200,
    });
    sleep(0.4);
  });
}
