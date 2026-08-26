# okihaiban-web

Landing page for Okihaiban / 置き配番.

## Cloudflare Pages

- Framework preset: None
- Build command: leave blank
- Build output directory: `public`
- Production branch: `main`

Custom domains:

- Canonical: `https://okihaiban.com`
- `https://www.okihaiban.com` and `https://okihaiban-web.pages.dev` must permanently redirect to the canonical host in Cloudflare.

## SEO route gate

Run before committing LP or routing changes:

```sh
python3 tools/check_seo_routes.py
```

Run after the production deployment:

```sh
python3 tools/check_seo_routes.py --live
```
