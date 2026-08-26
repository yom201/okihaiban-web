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
