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
RUN uv pip install "fastmcp==3.4.2" --system

RUN useradd --create-home appuser \
    && mkdir -p /data \
    && chown -R appuser /app /data
USER appuser

# Persist FastMCP's OAuth proxy state (client registrations and encrypted
# upstream tokens) outside the container layer, so users stay authenticated
# across redeploys. Mount a volume at /data to make this effective.
ENV FASTMCP_HOME=/data

# Expose port 8080 (default for Cloud Run)
EXPOSE 8080

# Define the command to run the server
# This uses the entry point defined in pyproject.toml
CMD ["google-ads-mcp"]
