# Pre-Production Ingress and Edge Proxy Checklist

Use this checklist before promoting the data pipeline to a cloud/VPS hosting environment (AWS, GCP, Kubernetes, or standalone virtual servers). It ensures the Nginx edge proxy and upstream configurations are hardened, handle dynamic IP resolution correctly, and reuse connections optimally.

---

## DNS and Upstream Resolution

In Nginx Open Source, upstreams configured with static `server` names resolve once at startup or reload. If backends scale dynamically or their IPs change, Nginx will request stale IPs.

### Tradeoff: Dynamic DNS vs Keepalive
- **Static Upstreams (Current Dev)**: Uses `upstream backend { server ingestor:8000; keepalive 32; }`. Provides connection keepalives but does not dynamically re-resolve DNS when IPs change.
- **Dynamic Resolution**: Uses `resolver 10.0.0.2 valid=10s; set $backend_url http://ingestor:8000; proxy_pass $backend_url;`. Re-resolves DNS dynamically, but loses connection pooling (`keepalive` block).

### Checklist Items
- [ ] **Determine Ingress Architecture**: Decide if TLS terminates at a cloud load balancer (e.g., AWS ALB, Kubernetes Ingress) or at a VPS-level Nginx edge instance.
- [ ] **Configure Cloud Load Balancing**: If using AWS/GCP, terminate TLS at the ALB/NLB level and let the load balancer manage connection pooling to the target groups. Bypass Nginx edge containers if not doing custom path routing.
- [ ] **Kubernetes CoreDNS Resolution**: If deploying to Kubernetes, use an Ingress Controller (like Nginx Ingress or Traefik) which natively handles dynamic endpoints/service routing without resolver caching issues.
- [ ] **VPS / Standalone Resolver**: If using a standalone VPS with Nginx OSS proxying to Docker containers, configure Nginx to reload whenever containers scale or restart, or use a short TTL resolver with variables:
  ```nginx
  resolver 127.0.0.11 valid=10s;
  set $upstream_ingestor http://ingestor:8000;
  proxy_pass $upstream_ingestor;
  ```

---

## SSL/TLS Certificates and SANs

Using IP literals like `127.0.0.1` locally avoids DNS overhead but requires specific certificate Subject Alternative Names (SANs) for HTTPS.

### Checklist Items
- [ ] **Replace Development Certificates**: Remove `mkcert` CA and certificates from deployment bundles. Never commit or upload `localhost+2.pem` or any other local private key to production or cloud environments.
- [ ] **Use Certified CAs**: Issue production certificates using Let's Encrypt (via Certbot/ACM) or your cloud provider's certificate manager (e.g., AWS Certificate Manager).
- [ ] **Define Hostname Allow-lists**: Configure server names (`server_name api.example.com;`) explicitly. Do not routing requests based on IP address literals in public environments.
- [ ] **Strict HTTPS Redirection**: Keep HTTP-to-HTTPS redirects active:
  ```nginx
  server {
      listen 80 default_server;
      server_name _;
      return 301 https://$host$request_uri;
  }
  ```

---

## Connection Reuse and Tuning

Connection keepalives reduce latency and socket exhaustion under high load.

### Checklist Items
- [ ] **Keepalive Tuning**: Set `keepalive` values based on traffic volumes. For high-volume production gateways, consider raising `keepalive` up to `64` or `128` per upstream worker.
- [ ] **Keepalive Timeout**: Keep `keepalive_timeout` at a value balanced between TCP handshake savings and connection resource usage (typically `65s`).
- [ ] **Proxy Header Configuration**: Ensure `proxy_http_version 1.1` and `proxy_set_header Connection ""` are configured on all hot-path upstream proxies to enable connection reuse.

---

## Security Hardening (OWASP Ingress)

Before exposing the ingress point, apply standard reverse proxy hardening.

### Checklist Items
- [ ] **Disable Verbose Errors**: Set `server_tokens off;` to prevent Nginx from exposing its version number in error pages or headers.
- [ ] **Secure Headers**: Apply headers for modern browser security:
  ```nginx
  add_header X-Content-Type-Options "nosniff" always;
  add_header X-Frame-Options "DENY" always;
  add_header X-XSS-Protection "1; mode=block" always;
  ```
- [ ] **Rate Limiting zones**: Adjust the request rate limiting zones (`limit_req_zone`) to match production SLA thresholds rather than local development thresholds.
- [ ] **Request ID Tracing**: Keep `$request_id` forwarding enabled to trace calls from edge proxies down to individual services in application logs.
