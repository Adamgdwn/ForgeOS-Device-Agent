#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${repo_root}"

status=0

pass() {
  printf 'PASS %s\n' "$1"
}

fail() {
  printf 'FAIL %s\n' "$1" >&2
  status=1
}

find_python() {
  if [[ -x "${repo_root}/.venv/bin/python" ]]; then
    printf '%s\n' "${repo_root}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    return 1
  fi
}

python_bin="$(find_python)" || {
  echo "FAIL no Python interpreter found for governance checks" >&2
  exit 1
}

if [[ ! -f project-control.yaml ]]; then
  echo "FAIL project-control.yaml is missing" >&2
  exit 1
fi
pass "project-control.yaml present"

mapfile -t required_docs < <("${python_bin}" - <<'PY'
from pathlib import Path

lines = Path("project-control.yaml").read_text().splitlines()
in_required = False
for line in lines:
    stripped = line.strip()
    if stripped == "required_docs:":
        in_required = True
        continue
    if not in_required:
        continue
    if stripped.startswith("- "):
        print(stripped[2:].strip())
        continue
    if stripped and not stripped.startswith("#"):
        break
PY
)

if [[ "${#required_docs[@]}" -eq 0 ]]; then
  fail "required_docs list is empty or unreadable"
else
  missing_docs=()
  empty_docs=()
  for doc in "${required_docs[@]}"; do
    if [[ ! -f "${doc}" ]]; then
      missing_docs+=("${doc}")
    elif [[ ! -s "${doc}" ]]; then
      empty_docs+=("${doc}")
    fi
  done
  if [[ "${#missing_docs[@]}" -gt 0 ]]; then
    fail "missing required docs: ${missing_docs[*]}"
  elif [[ "${#empty_docs[@]}" -gt 0 ]]; then
    fail "empty required docs: ${empty_docs[*]}"
  else
    pass "required docs present"
  fi
fi

mapfile -t registry_docs < <("${python_bin}" - <<'PY'
from pathlib import Path

lines = Path("project-control.yaml").read_text().splitlines()
for section in {"model_registry:", "prompt_registry:"}:
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == section:
            in_section = True
            continue
        if not in_section:
            continue
        if stripped.startswith("- "):
            print(stripped[2:].strip())
            continue
        if stripped and not stripped.startswith("#"):
            break
PY
)

for doc in "${registry_docs[@]}"; do
  if [[ ! -s "${doc}" ]]; then
    fail "registry document missing or empty: ${doc}"
  fi
done
if [[ "${#registry_docs[@]}" -gt 0 ]]; then
  pass "agent registry docs present"
fi

if "${python_bin}" -m compileall -q app tests; then
  pass "python compile check"
else
  fail "python compile check"
fi

if "${python_bin}" -m pytest -q; then
  pass "test suite"
else
  fail "test suite"
fi

secret_pattern='(AWS_SECRET_ACCESS_KEY|BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY|api[_-]?key[[:space:]]*[:=][[:space:]]*["'\'']?[A-Za-z0-9_./+=-]{24,}|token[[:space:]]*[:=][[:space:]]*["'\'']?[A-Za-z0-9_./+=-]{32,}|secret[[:space:]]*[:=][[:space:]]*["'\'']?[A-Za-z0-9_./+=-]{24,})'
secret_hits="$(
  git ls-files -z \
    | xargs -0 grep -IEn "${secret_pattern}" 2>/dev/null \
    | grep -Ev '(^|/)(docs|tests)/|\.env\.example:' \
    || true
)"
if [[ -n "${secret_hits}" ]]; then
  printf '%s\n' "${secret_hits}" >&2
  fail "secret scan found possible secret material"
else
  pass "secret scan"
fi

if [[ "${status}" -eq 0 ]]; then
  echo "Governance preflight passed."
else
  echo "Governance preflight failed." >&2
fi
exit "${status}"
