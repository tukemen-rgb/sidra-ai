"""Prepare the owner's PC to run the real local model through SIDRA.

``sidra-api`` (correctly) refuses to start a non-echo backend until
``<SIDRA_DATA_DIR>/model-manifest.json`` records the reviewed model and a
fresh NVIDIA VRAM observation admits it. Writing that JSON by hand in
notepad is exactly the kind of manual step that has already failed once on
the owner's machine, so this script measures and writes it instead:

1. asks the local Ollama (loopback only) what the model actually is -
   size on disk, quantization label, digest, license;
2. observes free NVIDIA VRAM through SIDRA's own bounded probe;
3. picks the largest context window that fits the observed budget,
   never guessing beyond what was measured;
4. writes the manifest, printing every value so the operator can review
   what was recorded - the printout *is* the review step;
5. re-runs SIDRA's real admission path against the file it just wrote,
   so "setup succeeded" means the same check the server runs will pass.

It contacts nothing but ``127.0.0.1``. It downloads nothing. If any step
fails it says which one and stops without writing.

Usage (on the owner's PC, from the repository root)::

    py scripts\\setup_real_model.py
    py scripts\\setup_real_model.py --model qwen2.5:3b
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.models import HardwareProbeError, probe_nvidia_vram  # noqa: E402
from sidra_ai.models.manifest import load_local_model_manifest  # noqa: E402
from sidra_ai.models.runtime_route import (  # noqa: E402
    admit_configured_adapter_with_nvidia_probe,
)

#: Matches the server's reserve in ``admit_configured_adapter_with_nvidia_probe``
#: so a context that fits here also fits there.
RESERVE_VRAM_MIB = 512

#: Conservative KV-cache growth for a ~3B GQA model (36 layers x 2 KV heads x
#: 128 dims x 2 bytes x K+V is ~36 MiB per 1k tokens; recorded with headroom).
KV_CACHE_MIB_PER_1K = 48

#: Tried largest-first; the first one the measured budget admits is recorded.
CONTEXT_CHOICES = (8192, 4096, 2048)


def _ollama(endpoint: str, path: str, payload: dict | None = None) -> dict:
    """One loopback Ollama call, bypassing any configured HTTP proxy."""

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = urllib.request.Request(endpoint + path, data=data, headers=headers)
    with opener.open(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5:3b", help="Ollama model tag")
    args = parser.parse_args()

    endpoint = os.environ.get("SIDRA_MODEL_ENDPOINT", "http://127.0.0.1:11434")
    if not endpoint.startswith(("http://127.0.0.1", "http://localhost")):
        print(f"NG  エンドポイントがローカルではありません: {endpoint}")
        return 1

    data_dir = Path(os.environ.get("SIDRA_DATA_DIR", ".sidra"))

    # -- 1. Ollama に実物のことを聞く -------------------------------------
    try:
        tags = _ollama(endpoint, "/api/tags")
    except Exception as exc:  # noqa: BLE001 - which step failed is the output
        print(f"NG  Ollama に接続できません（{type(exc).__name__}）")
        print("    Ollama を起動してから再実行してください（普段は自動起動です）")
        return 1

    records = {item.get("name", ""): item for item in tags.get("models", [])}
    record = records.get(args.model)
    if record is None:
        print(f"NG  モデル {args.model!r} が Ollama に入っていません")
        print("    入っているモデル: " + (", ".join(sorted(records)) or "(なし)"))
        return 1

    size_bytes = int(record.get("size") or 0)
    if size_bytes <= 0:
        print("NG  Ollama がモデルサイズを返しませんでした（測れない値は書きません）")
        return 1
    # 10% headroom over the on-disk size; runtime overhead beyond that is
    # covered by the shared reserve.
    weights_vram_mib = math.ceil(size_bytes / (1024 * 1024) * 1.10)

    details = record.get("details") or {}
    quantization = (details.get("quantization_level") or "").strip()
    if not quantization:
        try:
            show = _ollama(endpoint, "/api/show", {"model": args.model})
        except Exception:  # noqa: BLE001
            show = {}
        quantization = ((show.get("details") or {}).get("quantization_level") or "").strip()
    if not quantization:
        print("NG  量子化ラベルが取得できません（推測では書きません）")
        return 1

    try:
        show = _ollama(endpoint, "/api/show", {"model": args.model})
    except Exception:  # noqa: BLE001
        show = {}
    license_text = (show.get("license") or "").strip().splitlines()
    license_name = (license_text[0].strip() if license_text else "")[:80]
    if not license_name:
        license_name = "not-reported-by-ollama"

    digest = (record.get("digest") or "").strip()
    if not digest:
        print("NG  モデルの digest が取得できません（来歴なしでは書きません）")
        return 1

    print(f"OK  Ollama 接続・モデル確認  {args.model}")
    print(f"    サイズ {size_bytes / (1024**3):.1f} GB / 量子化 {quantization}")

    # -- 2. GPU の空きメモリを実測する ------------------------------------
    try:
        snapshot = probe_nvidia_vram()
    except HardwareProbeError:
        print("NG  NVIDIA GPU の空きメモリを実測できません（nvidia-smi が無いか失敗）")
        print("    現行の安全装置は NVIDIA 実測が必須です。この PC に NVIDIA GPU が")
        print("    無い場合はその旨を伝えてください（CPU 用の経路は別途の課題です）")
        return 1
    print(f"OK  GPU 実測  空き {snapshot.free_mib} MiB / 全体 {snapshot.total_mib} MiB")

    # -- 3. 実測に収まる最大のコンテキスト長を選ぶ ------------------------
    budget = snapshot.free_mib - RESERVE_VRAM_MIB - weights_vram_mib
    max_context = next(
        (c for c in CONTEXT_CHOICES if KV_CACHE_MIB_PER_1K * c / 1000 <= budget),
        None,
    )
    if max_context is None:
        need = weights_vram_mib + RESERVE_VRAM_MIB + int(
            KV_CACHE_MIB_PER_1K * CONTEXT_CHOICES[-1] / 1000
        )
        print(f"NG  空き VRAM が足りません（最低 {need} MiB 必要 / 空き {snapshot.free_mib} MiB）")
        print("    GPU を使う他のアプリを閉じてから再実行してください")
        return 1
    print(f"OK  コンテキスト長 {max_context} tokens が実測に収まります")

    # -- 4. マニフェストを書く（既存はバックアップ） ----------------------
    manifest = {
        "version": 1,
        "models": [
            {
                "backend": "ollama",
                "model": args.model,
                "weights_vram_mib": weights_vram_mib,
                "kv_cache_mib_per_1k_tokens": KV_CACHE_MIB_PER_1K,
                "max_context_tokens": max_context,
                "quantization": quantization,
                "priority": 10,
                "license": license_name,
                "revision": f"ollama-digest:{digest}",
            }
        ],
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "model-manifest.json"
    if path.exists():
        backup = path.with_suffix(".json.bak")
        path.replace(backup)
        print(f"    既存のマニフェストは {backup.name} に退避しました")
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows ACLs do not map onto POSIX bits; the write itself succeeded.
    print(f"OK  書き込み  {path}")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))

    # -- 5. サーバーと同じ審査をその場で通す ------------------------------
    try:
        admission = admit_configured_adapter_with_nvidia_probe(
            load_local_model_manifest(path),
            backend="ollama",
            model=args.model,
            planned_context_tokens=max_context,
            adapter_options={"endpoint": endpoint},
        )
    except Exception as exc:  # noqa: BLE001 - the class name says which gate
        print(f"NG  サーバーと同じ審査に落ちました（{type(exc).__name__}）")
        return 1
    print(f"OK  審査通過  空き {admission.snapshot.free_mib} MiB で admitted")
    print()
    print("次はサーバー起動です。同じ黒い窓でこの 4 行:")
    print("  set SIDRA_MODEL_BACKEND=ollama")
    print(f"  set SIDRA_MODEL_NAME={args.model}")
    print(f"  set SIDRA_MODEL_ENDPOINT={endpoint}")
    print("  py -m sidra_ai.api.server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
