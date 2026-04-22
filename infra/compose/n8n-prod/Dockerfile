FROM n8nio/n8n:latest

USER root

# Install system dependencies (Alpine)
RUN apk add --no-cache bash nano python3 py3-pip git curl

# Install Firecrawl MCP
RUN npm install -g firecrawl-mcp

# Install Claude Code CLI
RUN curl -fsSL https://claude.ai/install.sh | bash

# Claude Code auth token
ENV ANTHROPIC_AUTH_TOKEN=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

ENV PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

# Enable community packages
ENV N8N_COMMUNITY_PACKAGES_ENABLED=true
ENV NODE_ENV=production
ENV CI=true

# Create custom directory
RUN mkdir -p /home/node/.n8n/custom && chown -R node:node /home/node/.n8n

USER node
