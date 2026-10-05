# Source me: per-OS virtualenv + a PATH that finds uv from GUI-launched editors.
# The checkout is shared between a macOS host and a Linux sandbox, so each OS
# keeps its own environment: .venv on Linux, .venv-mac on macOS.
case "$(uname -s)" in
  Darwin) UV_PROJECT_ENVIRONMENT=".venv-mac" ;;
  *)      UV_PROJECT_ENVIRONMENT=".venv" ;;
esac
export UV_PROJECT_ENVIRONMENT
PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.cargo/bin"
export PATH
if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install it: brew install uv  (or: curl -LsSf https://astral.sh/uv/install.sh | sh)" >&2
  return 1 2>/dev/null || exit 1
fi
