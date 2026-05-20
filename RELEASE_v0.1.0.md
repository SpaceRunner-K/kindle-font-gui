# v0.1.0

最初の公開版です。

## Highlights

- Kindle 向けフォント修正 GUI の初回リリース
- 1本または2本のフォントを単一フローで処理
- Family 名、style、weight mode、typographic IDs の設定に対応
- 保存前チェックを実装
- 保存後のファイル再読込チェックを実装
- Regular / Bold ペアの基本整合性を確認可能

## Included checks

### Pre-save

- Family 名の未設定検出
- style 重複検出
- 出力名衝突検出
- typographic IDs 保持時の不足警告

### Post-save

- `name ID 1/2/6`
- `usWeightClass`
- `fsSelection`
- `head.macStyle`
- 保存後ペアの family 一致

## Notes

- 現時点では Kindle 実機の全パターンを保証するものではありません。
- まずは OTF / TTF の name 系調整と検証を主対象にしています。
- フィードバック歓迎です。
