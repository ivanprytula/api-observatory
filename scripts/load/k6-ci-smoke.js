import http from 'k6/http';
import { check, fail, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const USERNAME = __ENV.K6_USERNAME;
const PASSWORD = __ENV.K6_PASSWORD;

export const options = {
  scenarios: {
    authenticated_smoke: {
      executor: 'constant-vus',
      vus: Number(__ENV.VUS || '3'),
      duration: __ENV.DURATION || '20s',
    },
  },
  thresholds: {
    checks: ['rate==1'],
    http_req_failed: ['rate==0'],
  },
};

/**
 * Register a disposable viewer and obtain the JWT used by every virtual user.
 *
 * This keeps the CI proof isolated and exercises the public auth bootstrap
 * flow without relying on a seeded administrator account.
 */
export function setup() {
  if (!USERNAME || !PASSWORD) {
    fail('K6_USERNAME and K6_PASSWORD are required');
  }

  const health = http.get(`${BASE_URL}/health`);
  if (!check(health, { 'health returns 200': (response) => response.status === 200 })) {
    fail(`health returned ${health.status}`);
  }

  const registration = http.post(
    `${BASE_URL}/api/v1/auth/register`,
    JSON.stringify({
      username: USERNAME,
      email: `${USERNAME}@example.com`,
      password: PASSWORD,
    }),
    { headers: { 'Content-Type': 'application/json' } },
  );
  if (!check(registration, {
    'registration returns 201': (response) => response.status === 201,
  })) {
    fail(`registration returned ${registration.status}`);
  }

  const login = http.post(
    `${BASE_URL}/api/v1/auth/token`,
    `username=${encodeURIComponent(USERNAME)}&password=${encodeURIComponent(PASSWORD)}`,
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
  );
  if (!check(login, {
    'login returns a JWT': (response) => (
      response.status === 200 && Boolean(response.json('access_token'))
    ),
  })) {
    fail(`login returned ${login.status}`);
  }

  return { accessToken: login.json('access_token') };
}

/**
 * Exercise an authenticated database-backed route. Liveness is checked once in
 * setup so the smoke stays below the health endpoint's 100-request-per-minute
 * protection. Latency is recorded but not yet enforced until baseline data is
 * collected.
 */
export default function ({ accessToken }) {
  const sources = http.get(`${BASE_URL}/api/v1/sources?limit=20`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  check(sources, {
    'authenticated sources read returns 200': (response) => response.status === 200,
  });

  sleep(0.1);
}
