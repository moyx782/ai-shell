#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash install.sh [--bin-dir DIRECTORY] [--binary FILE] [--install-opencode]

Install the native ai executable. No Python, Node.js, or Go runtime required.
  --bin-dir DIRECTORY  Install directory (default: ~/.local/bin).
  --binary FILE        Install a local executable instead of downloading.
  --install-opencode   Install OpenCode separately if it is missing.
  -h, --help           Show help.

Downloads show percentage, transfer speed, and estimated time remaining.
Existing ai files are backed up before replacement. No sudo is used.
EOF
}

version=0.2.0
bin_dir="$HOME/.local/bin"
source_file=""
install_opencode=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir|--binary)
      [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || { echo "Missing $1 value" >&2; exit 2; }
      if [[ "$1" == --bin-dir ]]; then bin_dir="$2"; else source_file="$2"; fi
      shift 2 ;;
    --install-opencode) install_opencode=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$(uname -s)" in
  Linux) target_os=linux ;;
  Darwin) target_os=darwin ;;
  *) echo 'Supported systems: Linux, macOS, and Windows through WSL.' >&2; exit 1 ;;
esac
case "$(uname -m)" in
  x86_64|amd64) target_arch=amd64 ;;
  arm64|aarch64) target_arch=arm64 ;;
  *) echo 'Supported architectures: x86_64 and arm64.' >&2; exit 1 ;;
esac

work_dir="$(mktemp -d)"
stage=""
cleanup() {
  [[ -z "$stage" ]] || rm -f -- "$stage"
  rm -rf -- "$work_dir"
}
trap cleanup EXIT

download() {
  command -v curl >/dev/null || { echo 'curl is required for downloads.' >&2; exit 1; }
  echo "Downloading: $1"
  # The standard meter shows %, bytes, speed, elapsed time, and time remaining.
  curl --fail --location --show-error --retry 3 --connect-timeout 20 \
    --output "$2" "$1"
}

if ! command -v opencode >/dev/null && [[ -x "$HOME/.opencode/bin/opencode" ]]; then
  export PATH="$HOME/.opencode/bin:$PATH"
fi
if ! command -v opencode >/dev/null && [[ -z "${AI_SHELL_BACKEND:-}" ]]; then
  if [[ "$install_opencode" == true ]]; then
    download https://opencode.ai/install "$work_dir/install-opencode.sh"
    bash "$work_dir/install-opencode.sh"
    export PATH="$HOME/.opencode/bin:$PATH"
    command -v opencode >/dev/null || { echo 'OpenCode was not found after installation.' >&2; exit 1; }
  else
    echo 'OpenCode is missing. Install it first, or rerun with --install-opencode.' >&2
    exit 1
  fi
fi

if [[ -z "$source_file" ]]; then
  asset="ai-$target_os-$target_arch"
  base_url="https://github.com/moyx782/ai-shell/releases/download/v$version"
  source_file="$work_dir/$asset"
  download "$base_url/$asset" "$source_file"
  download "$base_url/SHA256SUMS" "$work_dir/SHA256SUMS"
  expected="$(awk -v name="$asset" '$2 == name {print $1}' "$work_dir/SHA256SUMS")"
  [[ "$expected" =~ ^[0-9a-f]{64}$ ]] || { echo 'Missing or invalid checksum.' >&2; exit 1; }
  if command -v sha256sum >/dev/null; then
    actual="$(sha256sum "$source_file")"
  elif command -v shasum >/dev/null; then
    actual="$(shasum -a 256 "$source_file")"
  else
    echo 'SHA256 verification needs sha256sum or shasum.' >&2; exit 1
  fi
  [[ "${actual%% *}" == "$expected" ]] || { echo 'SHA256 mismatch; installation aborted.' >&2; exit 1; }
  echo 'SHA256 verified.'
fi

[[ -f "$source_file" ]] || { echo "Missing executable: $source_file" >&2; exit 1; }
mkdir -p "$bin_dir"
target="$bin_dir/ai"
[[ ! -d "$target" ]] || { echo "Cannot replace directory: $target" >&2; exit 1; }
stage="$(mktemp "$bin_dir/.ai-install-XXXXXX")"
cp "$source_file" "$stage"
chmod 755 "$stage"
"$stage" --version
if [[ -e "$target" || -L "$target" ]]; then
  backup="$target.backup-$(date -u +%Y%m%d-%H%M%S)-$$"
  cp -P "$target" "$backup"
  echo "Backup: $backup"
fi
mv -f "$stage" "$target"
stage=""
echo "Installed: $target"
printf '\nFor this terminal, run:\n  export PATH=%q:"$PATH"\n' "$bin_dir"
echo 'Add that line to ~/.bashrc or ~/.zshrc for new terminals.'
echo 'Then run: ai (or ai --plan). OpenCode uses your existing configuration.'
