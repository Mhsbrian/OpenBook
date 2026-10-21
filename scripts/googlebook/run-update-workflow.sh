#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Fixed offline build sandbox. No disk, USB, KVM or Docker socket passthrough.
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
DATA=$(realpath -e "${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}")
PROFILE="$R/config/image-bases/ruby-workflow-camera25.json"
IMAGE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["container_image"])' "$PROFILE")
[[ "$IMAGE" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "Pinned container digest required" >&2; exit 2; }
[[ "$(docker image inspect "$IMAGE" --format '{{.Id}}')" == "$IMAGE" ]]
exec docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,nosuid,nodev,size=512m -u "$(id -u):$(id -g)" \
  -e OPENBOOK_HOME="$DATA" -e OPENBOOK_WORKFLOW_CONTAINER_ID="$IMAGE" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$DATA:$DATA:ro" -v "$DATA/installer:$DATA/installer" -v "$R:$R:ro" \
  -w "$DATA/installer" "$IMAGE" python3 "$R/scripts/googlebook/update-workflow.py" "$@"
