#!/usr/bin/env bash
# bump-deb-version-docker.sh
# Use your Docker cross-build image to bump debian/changelog via `dch`.
# This does NOT require dch/devscripts on the host; only inside the image.
#
# Examples:
#   tools/bump-deb-version-docker.sh -i -m "Packaging tweaks"
#   tools/bump-deb-version-docker.sh -u 0.1.2 -m "New upstream release"
#   tools/bump-deb-version-docker.sh -p -n 2 -m "Sync with pyproject"
#   tools/bump-deb-version-docker.sh -s -m "Snapshot build"
#   tools/bump-deb-version-docker.sh -i -R
#
# Image selection:
#   - default IMAGE: rpi-cross:arm64-bkw   (override via --image or IMAGE env)
#   - default DOCKERFILE: docker/Dockerfile.deb.bookworm.arm64 (override via --dockerfile or DOCKERFILE env)
#
set -euo pipefail

# --- locate project root (script lives in PRJ/tools) ---
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
PRJ_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
cd "${PRJ_ROOT}"

IMAGE="${IMAGE:-rpi-cross:arm64-bkw}"
DOCKERFILE="${DOCKERFILE:-${PRJ_ROOT}/docker/Dockerfile.deb.bookworm.arm64}"

# Defaults for changelog bump
DIST="${DIST:-bookworm}"
MSG="${MSG:-Bump version.}"
DEB_REV=""
MODE=""
RELEASE="no"

usage() {
  cat <<'EOF'
Usage: bump-deb-version-docker.sh [options]

  -i                     Increment Debian revision only (packaging change)
  -u <version>           Set new upstream version (e.g. 0.1.2). Debian rev defaults to -1 unless -n is given
  -p                     Read upstream version from pyproject.toml ([project].version)
  -s                     Snapshot from pyproject version: <ver>+gitYYYYMMDD.HHMMSS.<hash>-<n>
  -n <N>                 Debian revision number (default 1 for -u/-p/-s; ignored for -i)
  -D <dist>              Distribution (default: bookworm)
  -m <message>           Changelog message (default: "Bump version.")
  -R                     Mark the entry as released (runs: dch -r -D <dist>)
  --image <name>         Docker image to use (default from $IMAGE or rpi-cross:arm64-bkw)
  --dockerfile <path>    Dockerfile to build the image if missing (default docker/Dockerfile.deb.bookworm.arm64)
  -h                     Help

Environment overrides:
  IMAGE, DOCKERFILE, DIST, MSG, DEBFULLNAME, DEBEMAIL
EOF
}

# Parse long options first
LONG_IMAGE=""
LONG_DOCKERFILE=""
POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) LONG_IMAGE="$2"; shift 2 ;;
    --dockerfile) LONG_DOCKERFILE="$2"; shift 2 ;;
    -i|-u|-p|-s|-n|-D|-m|-R|-h) POSITIONAL+=("$1"); shift ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done
set -- "${POSITIONAL[@]}"

if [[ -n "${LONG_IMAGE}" ]]; then IMAGE="${LONG_IMAGE}"; fi
if [[ -n "${LONG_DOCKERFILE}" ]]; then DOCKERFILE="${LONG_DOCKERFILE}"; fi

# Parse short options
while getopts ":iu:psn:D:m:Rh" opt; do
  case "$opt" in
    i) MODE="inc" ;;
    u) MODE="upstream"; UPSTREAM="$OPTARG" ;;
    p) MODE="pyproject" ;;
    s) MODE="snapshot" ;;
    n) DEB_REV="$OPTARG" ;;
    D) DIST="$OPTARG" ;;
    m) MSG="$OPTARG" ;;
    R) RELEASE="yes" ;;
    h) usage; exit 0 ;;
    \?) echo "[ERROR] Unknown option: -$OPTARG"; usage; exit 2 ;;
    :)  echo "[ERROR] Option -$OPTARG requires an argument."; usage; exit 2 ;;
  esac
done

if [[ -z "${MODE}" ]]; then
  echo "[ERROR] Pick a mode: -i | -u <ver> | -p | -s"
  usage
  exit 2
fi

# Ensure we have a changelog
if [[ ! -f debian/changelog ]]; then
  echo "[ERROR] debian/changelog not found. Run inside the project root."
  exit 1
fi

# Build the image if missing
build_image_if_missing() {
  if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "[INFO] Docker image '$IMAGE' found."
    return 0
  fi
  if [[ -n "${DOCKERFILE}" && -f "${DOCKERFILE}" ]]; then
    echo "[INFO] Building image '$IMAGE' from ${DOCKERFILE}"
    docker build -f "${DOCKERFILE}" -t "${IMAGE}" "${PRJ_ROOT}"
  else
    echo "[ERROR] Docker image '$IMAGE' not found and no Dockerfile available."
    echo "        Provide --image or --dockerfile."
    exit 1
  fi
}

build_image_if_missing

# Prepare env for container
ENV_ARGS=(
  -e DIST="${DIST}"
  -e MSG="${MSG}"
  -e MODE="${MODE}"
  -e DEB_REV="${DEB_REV}"
  -e RELEASE="${RELEASE}"
)

# Optional vars
if [[ -n "${DEBFULLNAME:-}" ]]; then ENV_ARGS+=(-e DEBFULLNAME="${DEBFULLNAME}"); fi
if [[ -n "${DEBEMAIL:-}" ]]; then ENV_ARGS+=(-e DEBEMAIL="${DEBEMAIL}"); fi
if [[ "${MODE}" == "upstream" ]]; then ENV_ARGS+=(-e UPSTREAM="${UPSTREAM}"); fi

# Do the bump inside the container
docker run --rm \
  -v "${PRJ_ROOT}":/src \
  -w /src \
  "${ENV_ARGS[@]}" \
  "${IMAGE}" \
  bash -lc '
set -euo pipefail

if ! command -v dch >/dev/null 2>&1; then
  echo "[ERROR] devscripts/dch not available in the container image."
  exit 1
fi

py_version() {
python3 - <<'"PY"'
import sys
ver = ""
try:
    import tomllib
    with open("pyproject.toml", "rb") as f:
        ver = tomllib.load(f).get("project", {}).get("version", "")
except Exception:
    try:
        import tomli as tomllib  # fallback if present
        with open("pyproject.toml", "rb") as f:
            ver = tomllib.load(f).get("project", {}).get("version", "")
    except Exception:
        pass
print(ver)
PY
}

git_hash() {
  git rev-parse --short HEAD 2>/dev/null || echo "nogit"
}

timestamp_utc() {
  date -u +%Y%m%d.%H%M%S
}

DIST="${DIST:-bookworm}"
MSG="${MSG:-Bump version.}"
MODE="${MODE:-}"
DEB_REV="${DEB_REV:-}"
RELEASE="${RELEASE:-no}"

case "${MODE}" in
  inc)
    echo "[INFO] dch -i -D ${DIST} ..."
    dch -i -D "${DIST}" "${MSG}"
    ;;
  upstream)
    : "${UPSTREAM:?UPSTREAM version required}"
    REV="${DEB_REV:-1}"
    NEWVER="${UPSTREAM}-${REV}"
    echo "[INFO] dch -v ${NEWVER} -D ${DIST} ..."
    dch -v "${NEWVER}" -D "${DIST}" "${MSG}"
    ;;
  pyproject)
    V="$(py_version)"
    if [[ -z "$V" ]]; then
      echo "[ERROR] Could not read [project].version from pyproject.toml"
      exit 1
    fi
    REV="${DEB_REV:-1}"
    NEWVER="${V}-${REV}"
    echo "[INFO] dch -v ${NEWVER} -D ${DIST} ..."
    dch -v "${NEWVER}" -D "${DIST}" "${MSG}"
    ;;
  snapshot)
    V="$(py_version)"
    if [[ -z "$V" ]]; then
      echo "[ERROR] Could not read [project].version from pyproject.toml"
      exit 1
    fi
    TS="$(timestamp_utc)"
    H="$(git_hash)"
    REV="${DEB_REV:-1}"
    NEWVER="${V}+git${TS}.${H}-${REV}"
    echo "[INFO] dch -v ${NEWVER} -D ${DIST} ..."
    dch -v "${NEWVER}" -D "${DIST}" "${MSG}"
    ;;
  *)
    echo "[ERROR] Unknown MODE: ${MODE}"
    exit 2
    ;;
esac

if [[ "${RELEASE}" == "yes" ]]; then
  echo "[INFO] dch -r -D ${DIST}"
  dch -r -D "${DIST}"
fi

echo "[OK] New version: $(dpkg-parsechangelog -S Version || true)"
'

echo "[DONE] debian/changelog updated."
