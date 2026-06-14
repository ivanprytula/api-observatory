import http from 'k6/http';
import { check, group, sleep } from 'k6';

export const options = {
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
    group_duration::['p(95)<600'],
  },
};

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const TOKEN = __ENV.BEARER_TOKEN || '';

const headers = {
  'Content-Type': 'application/json',
  ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
};

export function setup() {
  const res = http.post(
    `${BASE}/api/v1/auth/token`,
    'username=admin&password=admin123',
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
  );
  check(res, { 'login ok': (r) => r.status === 200 || r.status === 401 });
  const token = res.status === 200 ? res.json().access_token : '';
  return { token };
}

export default function (data: { token: string }) {
  const authHeaders = data.token
    ? { ...headers, Authorization: `Bearer ${data.token}` }
    : headers;

  group('health', () => {
    const health = http.get(`${BASE}/health`);
    check(health, {
      'health 200': (r) => r.status === 200,
    });
    sleep(0.5);
  });

  group('sources-read', () => {
    const sources = http.get(`${BASE}/api/v1/sources?limit=20`, {
      headers: authHeaders,
    });
    check(sources, {
      'sources 200': (r) => r.status === 200,
    });
    sleep(0.3);
  });

  group('observations-write', () => {
    const obs = {
      source: 'k6-load',
      raw_data: { ts: Date.now(), vus: __VU, iter: __ITER },
      tags: ['load', 'k6'],
    };
    const created = http.post(
      `${BASE}/api/v1/observations`,
      JSON.stringify(obs),
      { headers: authHeaders },
    );
    check(created, {
      'obs 201': (r) => r.status === 201,
      'obs has id': (r) => r.json().id !== undefined,
    });
    sleep(0.2);
  });

  group('observations-read', () => {
    const list = http.get(`${BASE}/api/v1/observations?limit=10`, {
      headers: authHeaders,
    });
    check(list, {
      'list 200': (r) => r.status === 200,
      'has items': (r) => Array.isArray(r.json().observations),
    });
    sleep(0.2);
  });

  group('scorecards', () => {
    const scorecards = http.get(`${BASE}/api/v1/scorecards?limit=10`, {
      headers: authHeaders,
    });
    check(scorecards, {
      'scorecards 200': (r) => r.status === 200,
    });
    sleep(0.4);
  });
}
