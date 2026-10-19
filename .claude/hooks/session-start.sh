#!/bin/bash
# Install the pinned environment so `pixi run -e dev check` works in a fresh cloud session.
#
# AGENTS.md mandates `pixi run -e dev check` before every commit, and README tells a
# contributor to curl the pixi installer. A fresh cloud container has neither, so the one
# command the operating manual requires fails with command-not-found until someone installs
# pixi by hand. A repo audit on 2026-10-18 hit exactly that. This hook closes the gap.
#
# It installs from the committed lockfile with --locked, which is what CI's setup-pixi does
# (`locked: true`). That is deliberate: a stale lock must fail here the same way it fails in
# CI, rather than being silently re-solved into a different environment. A green local run
# meaning a green CI run is a promise the lockfile makes, and a hook that re-solved would
# quietly break it.
#
# Only the `dev` environment is installed. The genomad, proviruses and vibrant environments
# pin 2022-era toolchains, are linux-64 only, and are needed by individual tasks rather than
# by `check` -- installing them here would cost every session minutes it does not need.
set -euo pipefail

# Local machines have their own setup; this is for cloud sessions only.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PIXI_BIN="$HOME/.pixi/bin"

if ! command -v pixi >/dev/null 2>&1 && [ ! -x "$PIXI_BIN/pixi" ]; then
  echo "session-start: installing pixi"
  # PIXI_NO_PATH_UPDATE because this hook writes PATH to CLAUDE_ENV_FILE instead; letting the
  # installer edit a shell profile would not reach the session's environment anyway.
  export PIXI_NO_PATH_UPDATE=1
  curl -fsSL https://pixi.sh/install.sh | bash
else
  echo "session-start: pixi already present"
fi

export PATH="$PIXI_BIN:$PATH"

# Persist for the session, so `pixi` resolves without the caller re-exporting it.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$PIXI_BIN:\$PATH\"" >> "$CLAUDE_ENV_FILE"
  # Mirrors pixi.toml's [activation.env], so a bare `python3 tools/...` behaves the way the
  # same command does inside a pixi task rather than failing on `import amazebio`.
  echo "export PYTHONPATH=\"${CLAUDE_PROJECT_DIR:-$PWD}/src\"" >> "$CLAUDE_ENV_FILE"
fi

cd "${CLAUDE_PROJECT_DIR:-$PWD}"
echo "session-start: installing the dev environment from pixi.lock"
pixi install --locked -e dev

echo "session-start: ready -- pixi run -e dev check"
