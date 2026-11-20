# FRA ⇄ 東京 最安値ウォッチ(2027/7/25–8/13)

出発: フランクフルト(+ケルン・デュッセルドルフ・ブレーメン・アムステルダム)

3時間ごとに Google フライト(SerpApi 経由)から往復価格を取得し、
全体の最安値・直行便の最安値を記録して GitHub Pages に表示します。
最安値が更新されると Issue が作られ、GitHub から通知が届きます。

## 設定
- `config.json` … 日程・空港。`nonstop_alert_eur` に数字(例 1200)を入れると、直行便がその金額以下のときにも通知。
- Secrets に `SERPAPI_KEY` を登録(Settings → Secrets and variables → Actions)。
- Settings → Pages → Branch: `main` / `(root)` で公開。
