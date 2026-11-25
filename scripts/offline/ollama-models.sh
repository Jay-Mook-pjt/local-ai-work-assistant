#!/usr/bin/env bash
# Back up / restore Ollama models without any network access.
#
#   scripts/offline/ollama-models.sh export <dest-dir> [model ...]   # default: qwen3:14b
#   scripts/offline/ollama-models.sh import <src-dir>                # into $OLLAMA_MODELS (default ~/.ollama/models)
#   scripts/offline/ollama-models.sh verify <dir>                    # check every blob's sha256
#
# Copies only the manifest(s) and the blobs they reference, and checks each blob
# against the sha256 digest in its name. Existing files are never deleted;
# import refuses to overwrite a blob whose content differs.
set -euo pipefail
SRC_MODELS="${OLLAMA_MODELS:-$HOME/.ollama/models}"
REG="registry.ollama.ai"

manifest_path() {  # qwen3:14b -> manifests/registry.ollama.ai/library/qwen3/14b
  local name="${1%%:*}" tag="${1#*:}"
  [[ "$1" == *:* ]] || tag=latest
  [[ "$name" == */* ]] || name="library/$name"
  echo "manifests/$REG/$name/$tag"
}

digests() {  # all blob digests referenced by a manifest file
  python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print("\n".join([m["config"]["digest"]]+[l["digest"] for l in m["layers"]]))' "$1"
}

check_blob() {  # <file> -> 0 if content matches the sha256 in its name
  local f="$1" want="${1##*/sha256-}"
  [[ "$(shasum -a 256 "$f" | cut -d' ' -f1)" == "$want" ]]
}

copy_model_tree() {  # <from-root> <to-root> <manifest-rel>
  local from="$1" to="$2" rel="$3" d blob
  [[ -f "$from/$rel" ]] || { echo "모델 manifest 없음: $from/$rel" >&2; exit 1; }
  mkdir -p "$to/$(dirname "$rel")" "$to/blobs"
  for d in $(digests "$from/$rel"); do
    blob="blobs/${d/:/-}"
    [[ -f "$from/$blob" ]] || { echo "blob 없음: $from/$blob" >&2; exit 1; }
    if [[ -f "$to/$blob" ]]; then
      check_blob "$to/$blob" || { echo "대상에 내용이 다른 blob이 있습니다 (덮어쓰지 않음): $to/$blob" >&2; exit 1; }
    else
      cp "$from/$blob" "$to/$blob.partial" && mv "$to/$blob.partial" "$to/$blob"
    fi
  done
  cp "$from/$rel" "$to/$rel"
}

verify_dir() {
  local dir="$1" n=0 m d
  while IFS= read -r m; do
    for d in $(digests "$m"); do
      check_blob "$dir/blobs/${d/:/-}" || { echo "손상: $dir/blobs/${d/:/-}" >&2; exit 1; }
      n=$((n + 1))
    done
    echo "  ✓ ${m#"$dir"/manifests/$REG/}"
  done < <(find "$dir/manifests" -type f)
  echo "[ollama-models] blob $n개 sha256 일치"
}

cmd="${1:-}"; shift || true
case "$cmd" in
  export)
    dest="${1:?대상 폴더를 지정하세요}"; shift
    models=("$@"); [[ ${#models[@]} -gt 0 ]] || models=(qwen3:14b)
    for m in "${models[@]}"; do echo "[ollama-models] export $m"; copy_model_tree "$SRC_MODELS" "$dest" "$(manifest_path "$m")"; done
    verify_dir "$dest" ;;
  import)
    src="${1:?원본 폴더를 지정하세요}"
    verify_dir "$src"
    while IFS= read -r m; do copy_model_tree "$src" "$SRC_MODELS" "${m#"$src"/}"; done < <(find "$src/manifests" -type f)
    echo "[ollama-models] $SRC_MODELS 로 복원 완료. 'ollama list'로 확인하세요 (Ollama 재시작 불필요)." ;;
  verify) verify_dir "${1:?폴더를 지정하세요}" ;;
  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
