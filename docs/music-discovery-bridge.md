# Music discovery — cloud Friday + optional Mac taste-cache

## Production flow (cloud-first)

```
Thu 19:00 Mac (optional launchd)
  sync_taste → update state/music-discovery/taste-cache/ → push

Fri 09:00 cron-job.org
  → GitHub music-discovery-prefetch.yml
    → materialize taste-cache → inbox/music-discovery/YYYY-MM-DD-context.json
    → OpenAI web_search → YYYY-MM-DD-raw.json (Bandcamp/YouTube/cover URLs)
    → HTTP-verify + slim → YYYY-MM-DD-synthesis.json
    → commit inbox/music-discovery: YYYY-MM-DD research pre-fetch
      → GitHub Action **Synthesize briefing** (Codex, no browsing)
        → briefings/music-discovery/YYYY-MM-DD.md
          → Resend email
```

The Mac job is a **nice-to-have**. Friday cloud pre-fetch runs from whatever taste-cache is already on `main`. Stale-by-a-week is fine.

Taste cache alone is **not** enough for synthesis. After the Cursor→Codex move, Codex cannot browse the web, so Friday pre-fetch must also run OpenAI `web_search` (`scripts/fetch_music_research.py`) and land verified Listen URLs in `*-synthesis.json`. Codex then picks 6 featured + 4 More listening from that pool.

## Taste cache

Committed under `state/music-discovery/taste-cache/`:

- `context.json` — axes, `known_labels`, `recent_taste`, recommendation `skip_list`, `library_skip`
- `taste-snapshot.md` — agent-readable taste (includes Recent taste 24mo + Familiar labels)

Seed / refresh locally:

```bash
cd /Users/inigo/Documents/Cursor/personal
source .venv/bin/activate
python3 music-library/scripts/refresh_taste_and_bridge.py --push
```

## Install optional Thursday launchd

```bash
# Remove old Friday/monthly agents if present
launchctl bootout gui/$(id -u)/com.inigo.music-discovery.friday-bridge 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.inigo.music-discovery.monthly-sync 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.inigo.music-discovery.friday-bridge.plist
rm -f ~/Library/LaunchAgents/com.inigo.music-discovery.monthly-sync.plist

cp /Users/inigo/Documents/Cursor/personal/music-library/launchd/com.inigo.music-discovery.thursday-cache.plist \
  ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u)/com.inigo.music-discovery.thursday-cache 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.inigo.music-discovery.thursday-cache.plist
```

Log: `~/Library/Logs/music-discovery-thursday-cache.log`

## cron-job.org (required for Friday)

Same pattern as culture/restaurants — see `docs/external-scheduling.md` for the music curl.

## Cloud synthesis

`.github/workflows/synthesize-briefing.yml` (Codex via API key). No separate music automation.
