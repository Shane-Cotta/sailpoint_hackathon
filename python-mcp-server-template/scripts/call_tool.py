#!/usr/bin/env python3
"""Call one MCP tool in-process and print its result -- no MCP client needed.

    python scripts/call_tool.py review_team_access '{"manager": "Douglas.Flores"}'
    python scripts/call_tool.py get_identity_access '{"identity": "Brandon.Mason", "kind": "privileged"}'

The quickest way to debug a tool: set a breakpoint in src/sailpoint_mcp/tools/
and run this under the debugger (VS Code: "Debug a tool call").
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sailpoint_mcp.server import build_server  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].strip() else {}

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    result = asyncio.run(build_server().call_tool(tool, args))

    # Prefer the structured result; fall back to the text content.
    result = result[1] if isinstance(result, tuple) else result
    payload = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if payload is None:
        payload = json.loads(result.content[0].text)
    if isinstance(payload, dict) and set(payload) == {"result"}:
        payload = payload["result"]
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
