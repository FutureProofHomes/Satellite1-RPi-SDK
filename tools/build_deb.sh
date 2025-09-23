#!/usr/bin/env bash
set -euo pipefail

# --- locate project root (script lives in PRJ/tools) ---
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
PRJ_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
OUT_DIR="${PRJ_ROOT}/build-assets"

IMAGE="${1:-${IMAGE:-rpi-cross:arm64-bkw}}" 
DOCKERFILE="${DOCKERFILE:-${PRJ_ROOT}/docker/Dockerfile.deb.bookworm.arm64}"
PASSTHRU_OPTS=() 

# --- helper: build image if missing ---
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
    echo "        Provide IMAGE or DOCKERFILE env/flags."
    exit 1
  fi
}

# default build flags if none given
if [[ ${#PASSTHRU_OPTS[@]} -eq 0 ]]; then
  PASSTHRU_OPTS=(-b -us -uc)
fi

mkdir -p "${OUT_DIR}"

build_image_if_missing

echo "[BUILD] Docker build using ${IMAGE}"
echo "[INFO] PRJ_ROOT = $PRJ_ROOT"

docker run --rm \
    -e DEB_BUILD_OPTIONS="${DEB_BUILD_OPTIONS:-nocheck}" \
    -v "${PRJ_ROOT}":/src \
    -v "${OUT_DIR}":/out \
    -w /src \
    "${IMAGE}" \
    bash -lc '
      set -euo pipefail
      echo "[INFO] Source: $(pwd)"
      echo "[INFO] dpkg-buildpackage"
      dpkg-buildpackage -b -us -uc
      mkdir -p /out
      shopt -s nullglob
      mv ../*.deb ../*.changes ../*.buildinfo /out/ 2>/dev/null || true
    '


echo "[DONE] Artifacts:"
ls -l "${OUT_DIR}" || true
