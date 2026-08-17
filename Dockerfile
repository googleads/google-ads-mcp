# Use a slim Python image
FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory in the container
WORKDIR /app

# Copy the project files into the container
COPY . .

# Install the project and its dependencies
# We use --system to install into the system Python environment in the container
RUN uv pip install --system .

# Codex CLI 0.146 reports the RFC 9207 `iss` value as missing from the local
# OAuth callback, even though FastMCP constructs the redirect with `iss` and
# advertises it as mandatory. This version-guarded compatibility layer only
# stops affected clients from requiring that response parameter.
RUN python -c "from importlib.metadata import version; from pathlib import Path; assert version('fastmcp') == '4.0.0b3'; p = Path('/usr/local/lib/python3.11/site-packages/fastmcp/server/auth/oauth_proxy/proxy.py'); s = p.read_text(); old = 'metadata.authorization_response_iss_parameter_supported = True'; new = 'metadata.authorization_response_iss_parameter_supported = False'; assert s.count(old) == 1; p.write_text(s.replace(old, new))"

LABEL io.google-mcp.workaround="openai-codex-0146-rfc9207-iss"

# Expose port 8080 (default for Cloud Run)
EXPOSE 8080

# Define the command to run the server
# This uses the entry point defined in pyproject.toml
CMD ["google-ads-mcp"]
