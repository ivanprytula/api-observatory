# Docker BuildKit & Security Scanning Setup Guide

Track: B — Engineering Execution

**Last Updated**: April 22, 2026
**Status**: Production Ready

> **Decision rationale**: See ADR 004 (Docker BuildKit) for the context, trade-off analysis, and rejected alternatives.

---

## Table of Contents

1. [Local Development Setup](#local-development-setup)
2. [Security Scanning Tools](#security-scanning-tools)
3. [Pre-Commit Hooks](#pre-commit-hooks)
4. [GitHub Actions Workflows](#github-actions-workflows)
5. [Troubleshooting](#troubleshooting)

---

## Local Development Setup

BuildKit is enabled by default in this project — see `DOCKER_BUILDKIT=1` in the Dockerfile.

---

## Security Scanning Tools

### 1. pip-audit (Python Dependency Scanner)

#### Installation

```bash
# One-time install in your environment
pip install pip-audit

# Or via uv (if using this project)
uv pip install pip-audit
```

---

### 2. Trivy (Container Image Scanner)

Scans Docker images for OS-level vulnerabilities, misconfigurations, and dependency vulnerabilities.

#### Installation (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y trivy
```

If your distro mirror does not provide Trivy, use Docker fallback:

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image ingestor:latest
```

**Download Binary**:

- [Trivy GitHub Releases](https://github.com/aquasecurity/trivy/releases)

---

## Pre-Commit Hooks

### Setup Pre-Commit Framework

**Installation**:

```bash
pip install pre-commit
```

**Initialize** (one-time per repository):

```bash
cd /home/$USER/<directory>/data-pipeline-async
pre-commit install
```

This creates `.git/hooks/pre-commit` automatically.

### Add pip-audit Hook

See `.pre-commit-config.yaml` in the repo root for the pip-audit hook configuration.

### Run Pre-Commit Manually

```bash
pre-commit run --all-files
```

---

## GitHub Actions Workflows

CI workflows are defined in `.github/workflows/security.yml` — see the file directly.

---

## Troubleshooting

### Issue: BuildKit Not Recognized

**Symptom**: Error: `unknown flag: --mount`

**Solution**:

```bash
# Verify BuildKit is enabled
export DOCKER_BUILDKIT=1
docker version | grep -i buildkit

# If not shown, enable it
export DOCKER_BUILDKIT=1
docker build -t test:latest .
```

---

### Issue: pip-audit Fails Unexpectedly

**Symptom**: `pip-audit: command not found`

**Solution**:

```bash
# Install pip-audit
pip install pip-audit

# Or verify it's in PATH
which pip-audit

# If using uv:
uv pip install pip-audit
```

---

### Issue: Trivy Takes Too Long

**Symptom**: Trivy scan takes 5+ minutes

**Solution**:

```bash
# Update Trivy DB (cached, usually fast)
trivy image --download-db-only

# Scan with less detail (faster)
trivy image --severity HIGH,CRITICAL ingestor:latest

# Skip certain checks
trivy image --skip-update ingestor:latest
```

---

### Issue: Pre-Commit Hook Blocks Commit

**Symptom**: `pre-commit run` fails on pip-audit

**Solution**:

```bash
# Check vulnerability details
pip-audit --desc

# Fix dependencies
pip install --upgrade <package-name>

# Or skip hook for this commit (use sparingly)
git commit -m "fix: temporary skip" --no-verify
```

---

## Best Practices

1. **Run security scans locally first**: `pre-commit run --all-files` before pushing
2. **Update Trivy DB regularly**: `trivy image --download-db-only` (monthly)
3. **Monitor CVE announcements**: Subscribe to Python package security lists
4. **Set exit code strategically**:
   - Local dev: `exit-code: 0` (warn only)
   - CI/CD main: `exit-code: 1` (block merge)
5. **Review SARIF reports**: Check GitHub Code Scanning tab after each scan

---

## Additional Resources

- [Docker BuildKit Documentation](https://docs.docker.com/build/buildkit/)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
- [pip-audit Documentation](https://github.com/pypa/pip-audit)
- [OWASP Top 10 - Vulnerable Components](https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components/)
- [GitHub Code Scanning](https://docs.github.com/en/code-security/code-scanning)
