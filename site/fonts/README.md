# Self-hosted webfonts

Release 3 / Workstream B, step B3. These files are vendored deliberately: the site previously
pulled Libre Franklin and IBM Plex Mono from Google Fonts, which added a third-party connection
(two preconnects, a stylesheet round trip, then the font files) to the critical path of every
page. Self-hosting removes that origin entirely, so the fonts arrive on the same connection as
the HTML and can be preloaded and cached immutably.

## What is here, and why these faces

| File | Role | Where it renders |
| --- | --- | --- |
| `source-serif-4-latin-400-normal.woff2` | display, regular | `.lede` and `.prose` editorial text |
| `source-serif-4-latin-600-normal.woff2` | display, semibold | `h1`, `h2`, `h3`, `.brand`, panel and card headings |
| `ibm-plex-mono-latin-500-normal.woff2` | figures and metadata | `.fig`, `.mono`, `.finding-stat`, verdict pills, source lines, footer |

Only these three faces are used by the stylesheet, so only these three ship. Weights 400 and 600
are the only display weights the CSS asks for, and IBM Plex Mono is only ever used at 500.
No italic face is loaded: the three italic rules in `components.css` mark suppressed or
insufficient-data cells, and they render in the system UI stack, which has real italics.

The UI stack (body text, labels, buttons, navigation) is the platform system font and downloads
nothing. Libre Franklin has been removed and Sora is deliberately not loaded.

## Subset

Latin only. The site publishes US federal education data in English, so the latin subset covers
the content. Institution names occasionally carry accented characters, which latin covers.

## Provenance

Extracted from the Fontsource npm packages, which repackage the upstream Google Fonts releases
without modification:

* `@fontsource/source-serif-4` version 5.3.0
* `@fontsource/ibm-plex-mono` version 5.3.0

To refresh, install those package versions and copy the matching `files/*-latin-*-normal.woff2`
into this directory, then re-run the test suite. The bytes are not modified or re-subset here, so
the files can be diffed against the upstream packages.

## Licences

Both families are licensed under the SIL Open Font License 1.1, which permits self-hosting and
redistribution. The upstream licence texts ship alongside the fonts:

* `OFL-source-serif-4.txt` (Source Serif 4, Adobe)
* `OFL-ibm-plex-mono.txt` (IBM Plex Mono, IBM Corp.)

## Caching

`site/_headers` serves `/fonts/*` as immutable for a year. That is safe because the filenames
carry the weight and subset, so a different face is a different URL. If a family is ever updated
in place, change the filename rather than the bytes.
