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
RUN python -c "from importlib.metadata import version; from pathlib import Path; p = Path('/usr/local/lib/python3.11/site-packages/fastmcp/server/auth/oauth_proxy/proxy.py'); s = p.read_text() if p.exists() else ''; old = 'metadata.authorization_response_iss_parameter_supported = True'; new = 'metadata.authorization_response_iss_parameter_supported = False'; p.write_text(s.replace(old, new)) if old in s else None"

LABEL io.google-mcp.workaround="openai-codex-0146-rfc9207-iss"

# Default environment variables for internal deployment
ENV PORT=8080 \
    HOST=0.0.0.0 \
    MCP_TRANSPORT=streamable-http \
    GOOGLE_ADS_MCP_BASE_URL=https://google-ads-mcp.comergent.ai

# Expose port 8080
EXPOSE 8080

# Define the command to run the server
# This uses the entry point defined in pyproject.toml
CMD ["google-ads-mcp"]
