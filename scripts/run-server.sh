#!/bin/sh
# Start the SailPoint MCP server over stdio. Every client config points here
# (VS Code .vscode/mcp.json, Claude Code .mcp.json, the MCP Inspector).
# `uv run` creates and syncs the per-OS virtualenv on first use (see env.sh).
# Only stderr is used for output -- stdout is the protocol channel.
set -e
cd "$(dirname "$0")/.."
. scripts/env.sh
exec uv run --quiet --extra dev python -m sailpoint_mcp "$@"
