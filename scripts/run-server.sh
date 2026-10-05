#!/bin/sh
# Start the SailPoint MCP server over stdio. Every client config points here
# (VS Code .vscode/mcp.json, Claude Code .mcp.json, the MCP Inspector).
# `uv run` creates and syncs the per-OS virtualenv on first use (see env.sh).
# Only stderr is used for output -- stdout is the protocol channel.
set -e
cd "$(dirname "$0")/.."
. scripts/env.sh
# Opt-in debugging: set SAILPOINT_MCP_DEBUG_PORT (e.g. 5678) and attach a
# debugger to 127.0.0.1:<port> (VS Code: "Attach to MCP server").
if [ -n "${SAILPOINT_MCP_DEBUG_PORT:-}" ]; then
  export PYDEVD_DISABLE_FILE_VALIDATION=1
  exec uv run --quiet --extra dev python -Xfrozen_modules=off -m debugpy \
    --listen "127.0.0.1:${SAILPOINT_MCP_DEBUG_PORT}" -m sailpoint_mcp "$@"
fi
exec uv run --quiet --extra dev python -m sailpoint_mcp "$@"
