Status: Accepted

# 0004. Bundle the bgutil PO token provider

## Context

yt requires a GVS PO token ("proof of origin", minted by Google's
BotGuard script in the page) before most web-based player clients may fetch
their adaptive streams. yt-dlp 2026.08.19 ships the PO token framework but no
provider, so it silently skips every format that needs one.

That leaves videos requiring login capped well below what they offer.
Measured in October 2026 on a video requiring login that offers 2160p50,
with Firefox account cookies:

| Setup | Best format |
|---|---|
| yt-dlp signed-in defaults (`web_embedded`, `tv_downgraded`, `web`) | 360p (format 18, 27 MiB) |
| `web_safari` client, no token | 1080p50 H.264 HLS |
| Defaults plus a bgutil PO token (`web_creator` client) | 2160p50 VP9 (format 315, 886 MiB) |

The signed-out access mode (ADR 0003) cannot reach such videos at all, so
quality ranking had a single 360p candidate and no disagreement to report.
A PO token is not a cookie: it is minted per playback and, for these clients,
bound to the video ID, so browser cookies cannot supply it.

Constraints (source in brackets; load-bearing ones marked *):

- \* Tokens are needed per video, so per-download latency matters [yt-dlp PO
  Token Guide].
- \* Node.js is an optional, user-installed runtime today, already used for
  yt-dlp's n-challenge solver; packaged builds do not ship it [README].
- \* bgutil is GPL-3.0; FlowSnip source is MIT [repository licences].
- Up to 10 parallel downloads [`DownloadConfig.max_parallel_downloads`].
- Installers are built per OS in CI with PyInstaller [release workflow].

## Options

| Option | Fits when | Cost now | Extension path | Trade-off |
|---|---|---|---|---|
| a. bgutil (Brainicism) HTTP server, managed by FlowSnip | A maintained provider and per-video tokens are needed | Server build per OS (native `canvas` addon), process lifecycle, ~93 MB per installer | Swap to its script mode or another provider behind the same `base_url` argument | GPL-3.0 code in installers; needs Node 22+ |
| b. bgutil script mode | Tokens are rare | Build only | Same | Cold BotGuard start per token; upstream advises against concurrent use |
| c. yt-dlp-getpot-wpc | Chrome is present and a visible browser is acceptable | Plugin only | - | Experimental; opens a Chrome window the user must not close; MIT |
| d. bgutil Rust port | Node must be avoided | Static binary per OS | - | Last release 2026-03-12, before upstream's 2.0 BotGuard changes |
| e. No provider, add `web_safari` | 1080p is enough | One extractor argument | - | No 4K for videos requiring login |

## Decision

Option a, with bgutil pinned to 2.0.2 for both halves:

- The yt-dlp plugin (`bgutil-ytdlp-pot-provider==2.0.2`) is a locked Python
  dependency. yt-dlp discovers it on `sys.path`; packaged builds ship its
  `yt_dlp_plugins` sources as data files in the bundle root for the same
  discovery, since yt-dlp does not look inside PyInstaller's archive.
- The server is built by `installer/build_pot_server.py` from a pinned commit
  SHA (clone, `npm ci`, `tsc`, `npm prune --omit=dev`) into the gitignored
  `vendor/bgutil-server/`. `make bootstrap` and every release build job run
  it; the PyInstaller spec bundles the result. `canvas` uses N-API, so one
  build works with any Node 22+ on that OS and architecture. Release builds
  and the weekly dependency audit run `npm audit` on the server's production
  dependencies and fail on high or critical advisories.
- `flowsnip/pot_server.py` starts the server lazily, on the first yt
  download that needs it, with the Node runtime FlowSnip already detects. It
  listens on 127.0.0.1 only, on a free port, and the download passes
  `youtubepot-bgutilhttp:base_url` to yt-dlp. It is stopped when the app
  closes (and at interpreter exit), and restarted if it crashed. In frozen
  builds Node is launched with the user's original library search path, as
  yt-dlp does for its own child processes: the bundle's older `libstdc++`
  otherwise stops the system Node from starting on Linux.
- Without a token (no Node, Node older than 22, missing server files, or a
  server that does not come up), downloads proceed at the best quality
  reachable without one, and the activity log says once per session that
  higher quality needs Node.js 22 or newer.

## Consequences

- yt videos requiring login download at full resolution when Node 22+ is
  installed. Public videos are unaffected; their best path is still the
  signed-out clients, which need no token.
- Installers grow by about 93 MB uncompressed. Shrinking it (for example
  bundling the pure-JS dependencies with esbuild) is deferred.
- Distributed installers contain GPL-3.0 code. The installers carry the
  bgutil licence and a link to its source; FlowSnip's own source stays MIT.
- When yt changes BotGuard, tokens stop working until bgutil and then
  FlowSnip ship an update, the same dependency FlowSnip already has on
  yt-dlp. Plugin and server must be bumped together.
- The token server is unauthenticated, as upstream ships it; binding to
  loopback limits callers to local processes. If FlowSnip is killed without
  running its exit handlers, the Node process is orphaned until it is
  killed or the user logs out.
- Deno is not used for tokens even though FlowSnip accepts it for
  n-challenges; the HTTP server targets Node.
