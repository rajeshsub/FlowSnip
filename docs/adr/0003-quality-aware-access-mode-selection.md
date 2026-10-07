Status: Accepted

# 0003. Quality-aware access-mode selection for downloads

## Context

FlowSnip can reach a video in up to three access modes: signed in via browser
cookies, signed out, and signed in via an exported cookie file. Until now the
download worker tried them in a fixed order (browser cookies first) and moved
to the next mode only when the previous one raised an error whose text matched
an "auth keyword" list.

yt-dlp picks a different set of YouTube player clients depending on whether
the session is authenticated, and YouTube changes what each client is allowed
to return several times a year. In October 2026, with yt-dlp 2026.07.04, the
authenticated clients (`tv_downgraded`, `web_safari`) returned only
pre-merged HLS streams capped at 1080p H.264, while the signed-out client
(`android_vr`) listed the full adaptive ladder up to 2160p. Because the
signed-in attempt "succeeded", users with Browser Cookies set silently got
1080p for 4K videos. A dependency bump (2026.08.19) restores 4K in both modes
today, but the same silent downgrade has happened before and will recur the
next time the client capabilities shift in either direction.

The fallback was also fragile: it depended on matching yt-dlp's English error
text, which missed messages such as YouTube's "members-only" wording.

## Options

| Option | Fits when | Cost now | Trade-off |
|---|---|---|---|
| a. Probe every configured mode, download the best-ranked selection, fall back down the ranking on failure | Quality must not silently depend on which mode YouTube currently favours | One extra extraction request per video for each configured cookie source | Always touches account cookies when configured (same as before) |
| b. Signed-out first, cookies only when signed-out fails | Cookies are needed only for restricted content | Fastest | Silently downgrades when the public clients are the degraded ones (for example 360p-only during PO-token enforcement); loses Premium-only formats |
| c. Keep cookies-first and rely on bumping yt-dlp | Client behaviour is stable | None | The failure mode that already recurred |

## Decision

Option a. For each download, FlowSnip extracts once per configured access
mode (`extract_info(download=False)`), ranks each mode's selected formats by
(display height, fps, total bitrate), and downloads the best-ranked result by
reusing that mode's session and info dict (`process_ie_result(download=True)`),
so the download costs no extra request. Equal ranks keep the configured order
(browser cookies, signed out, cookie file). If the chosen download fails, the
next-ranked mode is tried. A mode that fails to extract never blocks the
others, so fallback no longer depends on error-message keywords; the keyword
list survives only to word the final "requires YouTube login" hint.

When modes disagree on resolution, the activity log says which mode offered
what and which one was used. After a download, ffprobe reads the finished file,
and a resolution below the selected one is logged as a warning, so a future
downgrade is visible rather than silent. A fallback attempt extracts again
rather than reusing the probe, so its signed media URLs are fresh.

Playlists are not compared. Their entries stay unresolved during the probe
(`extract_flat="in_playlist"`), so a playlist URL is not extracted in full once
per mode, and the first mode that sees the playlist downloads it lazily as
before. A mode that sees the playlist beats one that fell back to a single
video (for example a private list that only the signed-in session can see).

## Consequences

- Each configured cookie source adds one extraction request per download, on
  every site, not only YouTube. Users without cookies see no change in request
  count. Rate-limit-sensitive sites see the extra anonymous request too.
- Per-entry quality comparison for playlists is out of scope; playlist
  downloads keep the old single-mode behaviour.
- Quality no longer depends on whether YouTube currently favours
  authenticated or anonymous clients, as long as at least one configured mode
  can reach the best formats.
- If every mode is degraded (for example a stale yt-dlp against a YouTube
  change), the download still succeeds at the best available quality; the
  remedy remains updating yt-dlp. Packaged builds cannot update yt-dlp in
  place, so their update banner now points to a FlowSnip release instead of
  a pip call that cannot work there. A runtime yt-dlp updater for packaged
  builds is deliberately out of scope and needs its own ADR.
