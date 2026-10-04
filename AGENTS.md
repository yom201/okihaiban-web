# 置き配番LP 常設SEOゲート

LP、SEO、公開URL、リダイレクト、サイトマップを変更したら、完了前に次を実行する。

```sh
python3 tools/check_seo_routes.py
```

本番反映後は、公開配信も含めて次を実行する。

```sh
python3 tools/check_seo_routes.py --live
```

次の条件を緩めてはならない。

- サイトマップ掲載URLは、固有のHTML、title、description、h1、canonicalを持つ。
- 存在しないURLはトップページを200で返さず、`404`を返す。
- 旧URLは正規URLへ1回の`301`で移動する。
- `www.okihaiban.com`と`okihaiban-web.pages.dev`は`https://okihaiban.com/`へ恒久リダイレクトする。
- 正規URLはサイト内の少なくとも1ページからリンクされる。

Cloudflare Pagesの正規ホストは`https://okihaiban.com`。ホスト単位のリダイレクトは`_redirects`では扱えないため、CloudflareのゾーンルールまたはPages設定で維持する。

## 広い画面でのセクションの位置ずれ検査

LPのHTML・CSSやサイトマップを変更したら、完了前に次を実行する。サイトマップの全URLを幅2000pxと1440pxで測り、冒頭などのセクションの中身が本文の左端より60pxを超えて左へ広がる欠陥の再発を止める。

```sh
python3 tools/check_section_alignment.py
```

検査自体を変更したら、次の自己テストも実行する。一時コピーで正常状態のPASS、意図的な位置ずれのFAIL、復元後のPASSを確かめる。作業ツリーのpublic/は書き換えない。

```sh
python3 tools/check_section_alignment.py --self-test
```

しきい値を上げる、対象ページを外す、ブロックを除外する変更は禁止。Chrome不在、測定失敗、測定ページ数の不足、測定ブロックが2個未満の場合もFAILにし、検査を黙って飛ばしてはならない。

この検査は中身の左端のずれしか見ない。見出しの折れ方や見た目の崩れは画面写真で確認する。

## iOS 版の公開状態と検索向けページ

iOS 版が未公開のあいだ、検索向けページ（規約とプライバシーポリシーを除く）に iPhone・iPad・iOS・App Store を書かない。ゲートが赤にする。iOS 版を公開したら `tools/check_seo_routes.py` の `IOS_APP_RELEASED` を True にし、画質ページに注記『iPhoneはOSの制約により、監視やリモート撮影の利用には置き配番アプリを常に前面で立ち上げておく必要があります。』を太字で 1 回戻し、ほかのページの iPhone の説明も戻す。
