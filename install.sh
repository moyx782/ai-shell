#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash install.sh [--bin-dir DIRECTORY] [--install-opencode]

Install ai into ~/.local/bin by default. Requires Python 3.8+.
  --bin-dir DIRECTORY  Choose the directory for the ai executable.
  --install-opencode   Install OpenCode using its official installer if missing.
  -h, --help           Show this help.

Existing ai files are backed up before replacement. No sudo is used.
EOF
}

bin_dir="${HOME}/.local/bin"
install_opencode=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir)
      [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || { echo 'Missing --bin-dir value' >&2; exit 2; }
      bin_dir="$2"
      shift 2
      ;;
    --install-opencode) install_opencode=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$(uname -s)" in
  Linux|Darwin) ;;
  *) echo 'Supported systems: Linux, macOS, and Windows through WSL.' >&2; exit 1 ;;
esac

command -v python3 >/dev/null || { echo 'Install Python 3.8+ first.' >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else "Python 3.8+ is required")'
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_file="$project_dir/bin/ai"
[[ -f "$source_file" ]] || { echo 'Missing bin/ai; download or clone the complete project.' >&2; exit 1; }

if ! command -v opencode >/dev/null && [[ -x "$HOME/.opencode/bin/opencode" ]]; then
  export PATH="$HOME/.opencode/bin:$PATH"
fi
if ! command -v opencode >/dev/null; then
  if [[ "$install_opencode" == true ]]; then
    command -v curl >/dev/null || { echo 'curl is required to install OpenCode.' >&2; exit 1; }
    download="$(mktemp)"
    trap 'rm -f -- "$download"' EXIT
    curl --fail --show-error --silent --location https://opencode.ai/install -o "$download"
    bash "$download"
    export PATH="$HOME/.opencode/bin:$PATH"
    command -v opencode >/dev/null || { echo 'OpenCode was not found after installation.' >&2; exit 1; }
  else
    echo 'OpenCode is missing. Install it first, or rerun with --install-opencode.' >&2
    exit 1
  fi
fi

python3 - "$source_file" "$bin_dir" <<'PY'
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys
import tempfile

source = Path(sys.argv[1])
directory = Path(sys.argv[2]).expanduser().resolve()
directory.mkdir(parents=True, exist_ok=True)
target = directory / "ai"
if target.exists() and target.is_dir():
    raise SystemExit(f"Cannot replace directory: {target}")
if target.is_symlink() or target.exists():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = target.with_name(f"ai.backup-{stamp}")
    shutil.copy2(target, backup, follow_symlinks=False)
    print(f"Backup: {backup}")
fd, temporary = tempfile.mkstemp(prefix=".ai-install-", dir=directory)
try:
    with os.fdopen(fd, "wb") as output:
        output.write(source.read_bytes())
    os.chmod(temporary, 0o755)
    os.replace(temporary, target)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
print(f"Installed: {target}")
PY

"$bin_dir/ai" --version
printf '\nFor this terminal, run:\n  export PATH=%q:%q:"$PATH"\n' "$bin_dir" "$HOME/.opencode/bin"
printf 'To keep it for new terminals, add that export line to ~/.bashrc or ~/.zshrc.\n'
printf 'Configure your model provider with: opencode auth login\n'
printf 'Then enter your project directory and run: ai\n'
