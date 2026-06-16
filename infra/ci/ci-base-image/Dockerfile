# Multi-stage CI base image
# Stage 1: builder — includes build tools and dev libraries, runs `uv sync`
FROM python:3.14-slim@sha256:5b3879b6f3cb77e712644d50262d05a7c146b7312d784a18eff7ff5462e77033 AS builder

# Build-time arguments
ARG PIP_VERSION=26.0
ARG UV_VERSION=0.11.7

# Install build-time system dependencies (headers, compilers, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    postgresql-client \
    build-essential \
    g++ \
    libgdal-dev \
    gdal-bin \
    libgeos-dev \
    libproj-dev \
    libomp-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pip + uv in builder (used to populate installed site-packages)
RUN python -m pip install --upgrade pip==${PIP_VERSION} \
    && python -m pip install uv==${UV_VERSION}

# Set UV behavior for consistent builds
ENV UV_LINK_MODE=copy
ENV UV_COMPILE_BYTECODE=1

WORKDIR /workspace
COPY uv.lock pyproject.toml .python-version ./
COPY services/inference/pyproject.toml services/inference/pyproject.toml
COPY services/dashboard/pyproject.toml services/dashboard/pyproject.toml
COPY services/processor/pyproject.toml services/processor/pyproject.toml
COPY services/analytics/pyproject.toml services/analytics/pyproject.toml
COPY services/webhook/pyproject.toml services/webhook/pyproject.toml
COPY services/portal/pyproject.toml services/portal/pyproject.toml

# Run uv sync under buildkit cache to install all packages into the builder image
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-packages

# Tar the site-packages directory so the runtime stage can extract it
RUN python - <<'PY'
import sysconfig, subprocess, os
sp = sysconfig.get_paths()['purelib']
base = os.path.dirname(sp)
name = os.path.basename(sp)
subprocess.check_call(['tar', '-C', base, '-czf', '/tmp/site-packages.tar.gz', name])
print('Packed', sp)
PY


# Stage 2: runtime — small image without build tools, copies installed packages
FROM python:3.14-slim@sha256:5b3879b6f3cb77e712644d50262d05a7c146b7312d784a18eff7ff5462e77033 AS runtime

ARG PIP_VERSION=26.0
ARG UV_VERSION=0.11.7

# Install minimal runtime system packages (no compilers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    postgresql-client \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install pip and uv in the runtime image (uv used by CI jobs)
RUN python -m pip install --upgrade pip==${PIP_VERSION} \
    && python -m pip install uv==${UV_VERSION} \
    && rm -rf /root/.cache/pip

WORKDIR /workspace

# Copy the prepared site-packages from the builder and extract into the runtime's site-packages
COPY --from=builder /tmp/site-packages.tar.gz /tmp/site-packages.tar.gz
RUN python - <<'PY'
import sysconfig, subprocess, os
sp = sysconfig.get_paths()['purelib']
base = os.path.dirname(sp)
subprocess.check_call(['tar','-C', base, '-xzf', '/tmp/site-packages.tar.gz'])
print('Extracted into', sp)
PY

# Clean up
RUN rm -f /tmp/site-packages.tar.gz

# Default entrypoint for diagnostic checks
ENTRYPOINT ["sh", "-lc", "python --version && pip --version && uv --version"]
