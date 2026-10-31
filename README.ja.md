# vram16-measured — 「自分の GPU で動く？」に、実測だけで答える AI エージェントの skill

Claude Code・Codex・Cursor など、`SKILL.md` を読む AI エージェントに入れて使います。
「RTX 4060 で FLUX 動く？」「この PC で商品画像を作って」と頼むと、エージェントがあなたの GPU とメインメモリを調べ、**[実測ノート（vram16.ullu-egg.com）](https://vram16.ullu-egg.com/) で実際に動かした組み合わせだけ**から選びます。測っていない物は「測っていない」と答え、見当の数字は出しません。

## こんな人向け

- RTX 4060（8GB）・3060／4070（12GB）で、ComfyUI の画像生成を始めたい人
- 「8GB でも動く」「16GB 推奨」がばらばらの記事を読み比べて、自分の場合が分からない人
- 作った絵を売る・YouTube に使うので、**ライセンスまで確かめてから**選びたい人

## 中身

- **45 モデル・383 の測った組み合わせ**（RTX 5080 16GB。画像・編集・高画質化・動画・音声・音楽・LLM）。秒数・最大 VRAM・ライセンス・失敗の記録
- **8GB・12GB 相当の実測**: 人気の画像モデルと、動画の Wan 2.2 TI2V 5B（5 秒。文字から動画は 832×480 と 1280×704、画像から動画は 1280×704）を、VRAM に 7GiB／11GiB の上限をかけて動かした結果（[測り方](https://vram16.ullu-egg.com/feature/small-gpu-2026-10/)）。小さい GPU で本当に詰まるのは **VRAM ではなくメインメモリ**のことがある、まで言えます
- **配布ワークフロー 76 本**（ComfyUI の API 形式。公開前に同じ絵が出ることを確かめた物）
- ライセンスは記事が引いた条文から。「研究用だけ」のモデルを商用の頼みに出しません

## 例: ノートの RTX 4060 Laptop（8GB）・メモリ 16GB で画像を作りたい

```
python scripts/pick.py --task t2i --vram 8 --gpu-name "RTX 4060 Laptop" --ram 16 --top 3
1. Z-Image Turbo — int8 1024×1024: 5.18 s, 1st run incl. loading 14.95 s, peak VRAM 7.2 GB | commercial: yes (Apache License 2.0)
   basis: measured with VRAM capped to the 8GB class ...; LAPTOP GPU: ... expect it slower still
   system RAM: TIGHT: loading added 9.5GB of system RAM in the test; you have 16.0GB. Close other apps, or pick another
   ...
   skipped: FLUX.1 dev fp8: STOPPED at the 8GB level — stopped while loading: system RAM rose by about 32.0GB ...
```

エージェントは日本語でこう答えます（読み方は `SKILL.md` に書いてあります）:

> 8GB 相当に絞って実際に動かした中では、Z-Image Turbo（int8）が 1 枚 5.18 秒・VRAM 7.2GB でした。ただしこの秒数は試験の PC（RTX 5080）の速さで、ノートの 4060 ではさらに数倍かかります。メモリ 16GB ではぎりぎりなので、ブラウザを閉じてから動かしてください。FLUX.1 dev は 8GB 相当で、VRAM ではなくメインメモリが足りずに止まりました。

## あなたの PC での秒数

実測の秒数は試験の PC の数です。ComfyUI が動いていれば、測った配布ワークフローを 1 本 3 回回すだけ（約 1 分）で、以後すべての候補を**あなたの PC の秒数**で言い直します。

```
python scripts/run_comfy.py --workflow https://vram16.ullu-egg.com/workflows/sd3.5-large-turbo_1024.json --calibrate
```

速さの比はあなたの PC の中（`~/.vram16-measured/calibration.json`）にだけ残り、どこにも送りません。

## 入れ方

このフォルダを、エージェントの skill の置き場に写します（Claude Code なら `~/.claude/skills/vram16-measured/`）。Python 3.9 以上だけで、追加のパッケージは要りません。`run_comfy.py` は ComfyUI が動いている時だけ使います。

## 数字の取り方

生成時間は、モデルを読み込んだ後の 2 枚目と 3 枚目の平均です（毎回プロンプトを変えるので、文章の解析も毎回走ります）。読み込みを含む 1 枚目は別に載せています。詳しくは[測り方](https://vram16.ullu-egg.com/about/)。

## ライセンス

コードは MIT。データ（`data/measured.json`）は CC BY 4.0 で、「vram16.ullu-egg.com」の表示をお願いします。
