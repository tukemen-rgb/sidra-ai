# 初回実回答 手順書（社長機 / GTX 1660 6GB）

目的はただ一つ: **安全設計（reviewed manifest + NVIDIA VRAM プローブ + fail-closed）を
一切変えずに、引用付きの「本物の回答」を 1 件生成すること。**
賢い回答である必要はない。完走の証拠が取れれば成功。

前提（2026-08-22 社長実測で確認済み）:

- GPU: GeForce GTX 1660 系、VRAM 6144 MiB（空き約 5.8 GB）
- ドライバ 462.30 / CUDA 11.2（2021 年版。手順 1 参照）
- Python 3.11+ と pip は e5 セットアップ時に確認済み
- 埋め込みモデルは `C:/sidra/model` に設置済み（`SIDRA_EMBEDDING_MODEL_PATH` 設定済み）

所要: 30〜60 分（モデルダウンロード約 2 GB を含む）。

---

## 1. NVIDIA ドライバを更新する（推奨・先にやる）

462.30 は 2021 年のドライバで、現行の Ollama が同梱する CUDA ランタイムより古い。
このままだと Ollama が GPU を認識せず CPU で動いてしまう可能性が高い。

- https://www.nvidia.co.jp/Download/index.aspx で GTX 1660 用の最新 Game Ready /
  Studio ドライバを入れて再起動。
- 更新後にコマンドプロンプトで `nvidia-smi` を実行し、Driver Version が
  530 以上になっていることを確認。

（更新しないで進めても手順は失敗しないが、後で Ollama が
"no compatible GPU" 相当の挙動になったらここに戻る。）

## 2. Ollama を入れてモデルを取得する

1. https://ollama.com/download から Windows 版をインストール。
2. コマンドプロンプトで:

```
ollama --version
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama list
```

- モデル選定の理由: 6 GB VRAM に対し重み約 2.1 GiB + 8k コンテキストの
  KV キャッシュ約 0.3 GiB で、予約 512 MiB を引いた使用可能枠（約 5.3 GiB）に
  大きな余裕を残して収まる、日本語が通じる最小クラスの instruct モデル。
  最初の 1 件は「収まることが確実」を優先する。
- `ollama list` の **ID 列（12 桁の英数字）を控える**。manifest の provenance
  （`revision`）に使う。

## 3. VRAM 使用量を実測する

manifest の数字は推測ではなく実測で書く（SIDRA の設計方針）。

```
ollama run qwen2.5:3b-instruct-q4_K_M "こんにちは。1行で自己紹介して。"
ollama ps
```

- `ollama ps` の SIZE と「GPU/CPU」列を確認。**100% GPU** であること
  （CPU が混ざっていたら手順 1 のドライバ更新に戻る）。
- SIZE（例: 3.1GB）を控える。これが「重み + 既定コンテキスト」の実測値。

## 4. sidra-ai を入れる

```
git clone https://github.com/tukemen-rgb/sidra-ai
cd sidra-ai
pip install -e ".[dev]"
```

## 5. manifest を書く（これがレビュー）

`sidra-ai` フォルダ直下に `.sidra` フォルダを作り、
`.sidra\model-manifest.json` を以下の内容で保存する。
**保存する前に数字を手順 3 の実測と突き合わせること。この確認行為が
「reviewed manifest」のレビューにあたる。**

```json
{
  "version": 1,
  "models": [
    {
      "backend": "ollama",
      "model": "qwen2.5:3b-instruct-q4_K_M",
      "weights_vram_mib": 2600,
      "kv_cache_mib_per_1k_tokens": 40,
      "max_context_tokens": 8192,
      "quantization": "q4_K_M",
      "priority": 1,
      "license": "apache-2.0",
      "revision": "<ollama list の ID をここに>"
    }
  ]
}
```

- `weights_vram_mib` 2600 は実測 SIZE より大きい安全側の宣言。実測が
  2600 MiB を超えていたら実測+300 程度に引き上げる。
- 起動時の admission は `weights + ceil(8192/1000)×40 = 2920 MiB` を
  「観測した空き VRAM − 予約 512 MiB」と比べる。6 GB 機なら通る。
  他のアプリが VRAM を大量に使っていると落ちるので、ゲーム等は閉じておく。

## 6. 起動する

同じコマンドプロンプトで（e5 の環境変数が既に入っている窓なら埋め込みも同時に有効）:

```
set SIDRA_MODEL_BACKEND=ollama
set SIDRA_MODEL_NAME=qwen2.5:3b-instruct-q4_K_M
sidra-api
```

- 起動が `ModelUnavailableError`（fail-closed の一定文言）で落ちる場合の
  切り分け順: (1) Ollama が起動しているか（`ollama ps` が応答するか）
  (2) manifest の backend/model が環境変数と**完全一致**か
  (3) `nvidia-smi` が動くか（プローブは nvidia-smi を直接叩く）
  (4) VRAM 空きが 3.5 GB 以上あるか。
- 詳細が出ないのは仕様（ローカルパスやモデル名をログに漏らさない設計）。

## 7. 1 リポジトリを索引して、1 問聞く

別のコマンドプロンプトを開いて:

```
curl -X POST http://127.0.0.1:8000/v1/github/analyze -H "Content-Type: application/json" -d "{\"repository\": \"tukemen-rgb/site\"}"
```

（自宅回線の匿名クォータ 60 回/時で足りる。トークン不要。）

索引が終わったら:

```
sidra-ask "GAMEYARD の north star metric は何か"
```

## 8. 成功の証拠を貼る

以下をそのままチャットに貼る（トークン類は含まれないので貼ってよい）:

1. `sidra-ask` の出力全体（回答 + 引用）
2. `ollama ps` の出力（実測 VRAM）
3. `sidra-api` 起動時のログの最初の数行

**成功条件は「引用付きの実回答が 1 件、echo ではないモデルから出たこと」。**
回答の質はこの段階では問わない。質・速度の比較はこの完走が証拠化されてから。

## うまくいかないとき

- どの手順で何が出たかをそのまま貼ってもらえれば、こちらで切り分けます。
- **どの失敗でも設計は緩めない。**CPU フォールバックや admission の迂回は
  この手順書の範囲外（それは E 節の (b) 判断に戻る）。
