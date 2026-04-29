# Sonata Changelog

Personal music player PWA. Streams from Jellyfin on NAS via the Sonata Bridge.

---

## v0.14 — 29 April 2026

### Bridge integration
The Sonata Bridge is now Sonata's only point of contact with the outside world. The browser holds no API keys and talks to no third-party services directly. Every Jellyfin call, every fanart.tv lookup, and every MusicBrainz lookup is routed through the bridge running on the NAS, which terminates HTTPS via Let's Encrypt and attaches the relevant credentials server-side.

### Settings simplification
- Three fields removed from Settings (Jellyfin Local URL, Jellyfin Tailscale URL, Jellyfin API Key) and replaced with a single Bridge URL field
- fanart.tv API key field removed entirely. The bridge holds the key; Sonata just calls /fanart/:mbid on the bridge
- Connect & Load handler clears all the legacy localStorage entries (sonata_jf_url, sonata_jf_tailscale, sonata_jf_key, sonata_fanart_key) when a bridge URL is saved, so old credentials don't linger

### Wins from doing this properly
- iPhone Safari works without certificate warnings or Mixed Content blocks
- Artist photography starts working again — fanart.tv's broken CORS headers are no longer in the picture, since the bridge handles the call server-side
- MusicBrainz calls are centrally rate-limited at 1/sec across all clients, with a proper User-Agent header that MB actually wants
- API keys live in /volume1/sonata-bridge/.env on the NAS (chmod 600), not in browser localStorage

### Bridge endpoints
- /health — status and uptime check
- /jellyfin/* — proxied Jellyfin API with API key attached server-side (header for fetch, query string for &lt;img&gt;/&lt;audio&gt; tags)
- /fanart/:mbid — proxied fanart.tv lookup with 24h response cache
- /mbid?artist=NAME — proxied MusicBrainz lookup with 24h response cache and central 1/sec rate limit
- /stats — cache sizes and memory usage

### Migration notes
On first load of v0.14, you will need to open Settings and paste your bridge URL (e.g. https://yourname.duckdns.org:5443). After that, Sonata fetches the library through the bridge and the userId is re-resolved automatically. The library cache survives the change so no full re-fetch is needed.

---

## v0.13 — 28 April 2026

### Desktop Player Redesign
- Bottom player rebalanced into three equal thirds: track info on the left, playback controls + progress bar in the middle, volume + speaker selector on the right
- Track info section is no longer fixed at 280px — it now uses its third of the available width like everyone else, so on wide screens the title and artist have proper room to breathe
- Cast button moved into the playback controls cluster, sitting just after the repeat icon. It's now icon-only (no "CAST" text) since it's clearly a playback control by position. Stays blue when a Sonos room is connected, like the existing shuffle-on / repeat-on states

### Capybara Volume Slider
- Volume control is significantly bigger: 38px tap target (up from 6px), 14px-tall track, properly clickable
- A small capybara photo rides the slider, sitting on the fill edge wherever the volume happens to be
- Capybara does a little bob animation when the volume is changed
- Click anywhere on the track to set volume; click and hold to drag the capybara along
- Touch drag support too, in case the desktop is touch-enabled

---

## v0.12 — 28 April 2026

### Quickfire Playlist (new)
- New Quickfire Playlist button on the Home page, sat next to Wheel of Fortune
- Tap it to enter selection mode: an action bar appears at the top of the picks grid, the album tiles become tappable for selection rather than playback, and a tick badge appears on each chosen tile
- Select exactly 4 albums from today's "Picked for you" set (the selection is constrained to the random daily picks, not the wider library)
- Selecting a 5th album shows a toast asking you to deselect one first
- A "Cancel" button bails out, a "Create & Play" button activates once 4 are chosen
- On Create: every track from the 4 albums is gathered, Fisher-Yates shuffled, and saved as a new playlist named "DD/M Quickfire N" (e.g. "28/4 Quickfire 1"). The number auto-increments per day so successive Quickfires on the same day get sequential names
- The new playlist appears in the sidebar / mobile playlist list immediately and starts playing in shuffled order
- Routes straight into the playlist's track listing view after creation, so you can see what you just made
- Saved to Jellyfin via a single bulk-add call (no 4-times-around-the-loop) when connected, or kept local-only as a fallback
- Reshuffle button is hidden during selection so you can't pull the rug out from your own choice

---

## v0.11.3 — 28 April 2026

### Artist Photography
- MusicBrainz query now uses unquoted, special-character-stripped lookup so "Beatles" finds "The Beatles", "AC/DC" doesn't break the Lucene parser, and so on
- Removed the User-Agent header from MusicBrainz fetch — browsers refuse to set it on `fetch()`, and trying to do so could cause requests to fail outright in some environments. This is the most likely root cause of the 0-out-of-3,021 result the previous Fetch All run produced
- Transient errors (HTTP 5xx, 429 rate-limit, network failures) no longer poison the cache as "no image". The result is only cached when it's a definitive answer (200 with no match, 404, or a real image URL). Anything else gets retried on the next pass
- New "Retry failed lookups" button in Settings, next to "Clear image cache". Clears only the null entries from both the MusicBrainz and fanart.tv caches, leaving any real hits in place. Designed for exactly the situation above: a previous Fetch All filled the cache with false negatives, and you want to re-attempt them without losing legitimate hits
- Console warnings logged for each transient failure during a fetch, so it's clear in DevTools whether MusicBrainz, fanart.tv, or the network is the culprit
- Diagnosis revealed that fanart.tv currently returns broken CORS headers (`Access-Control-Allow-Origin: *, *`) which any browser refuses to honour. v0.14 solves this by routing through the bridge

---

## v0.11.2 — 28 April 2026

### Wheel of Fortune
- Now navigates to the album track listing after spinning, so the listener can see what they're about to hear
- Works for regular albums, compilations and DJ mixes alike — routes to the right view in each case
- Sidebar and bottom nav highlighting updates to match the new view

### Home Picks Persistence
- "Picked for you" tiles now stay the same all day, midnight to midnight (local time)
- First open of a new day generates a fresh set of 12 picks
- Manual Reshuffle button still works as an immediate override and the new picks persist for the rest of the day too
- Stored in localStorage with a date stamp; rolls automatically when the date changes
- Survives a manual library refresh — picks are validated against the freshly-built indexes and any albums that no longer resolve are quietly topped up

---

## v0.11.1 — 28 April 2026

### Loading Screen
- Test card now shows on every cold open, not just first install or manual refresh
- Minimum display time of 1.5 seconds so the test card actually has a moment to be seen
- If the underlying load takes longer (e.g. first-run full fetch, slow network), the screen stays up until the load completes — the 1.5 seconds is a floor, not a ceiling
- Status text under the card progresses through "tuning in…" → "reading library…" → "Connecting to Jellyfin…" → "Loading library…" as appropriate
- Background sync remains silent — the splash only appears on app open, not during the 2-second-later silent sync

---

## v0.11 — 28 April 2026

### Library Refresh
- Refresh button removed from desktop top bar and mobile top bar (was too easy to hit by accident)
- New Library section in Settings with a deliberate Refresh Library button
- Confirmation modal warns that refresh takes around 20 minutes and Sonata is unusable until it finishes
- Status line shows track count, album count, and when the library was last refreshed (e.g. "today at 14:32", "yesterday at 09:15", "26 Apr at 18:40")
- Last-refresh timestamp stored in localStorage and updated on every successful fetch
- Clarifying note explains that the silent background sync usually picks up new music automatically, so manual refresh is rarely needed

### Album Artwork
- Album tiles in the Albums view now show real Jellyfin artwork (previously fell back to the Mondrian generator)
- Same fix applied to Compilations tiles, DJ Mixes (level 2) tiles, and the Home view "Picked for you" tiles
- Artwork URL now stored in the pre-built indexes per album, so no extra lookups at render time
- Mondrian art still used as the fallback when no artwork is available

---

## v0.10 — 28 April 2026

### Loading Screen
- Spinner replaced with the actual BBC Test Card F image
- Faint CRT scanlines and vignette over the image for the right vintage feel
- Status text below the card with a typewriter-style blinking cursor

### Home View (new)
- Now the default landing screen, replacing All Tracks
- "Hello." header with live track and album counts
- Wheel of Fortune button: picks a random album and plays it from track 1
- 12 random album tiles ("Picked for you") drawn from albums, compilations and DJ mixes
- Reshuffle button refreshes the picks on demand

### Performance
- Pre-built library indexes built once after fetch or cache load
- Album, Artist, Compilations and DJ Mixes views now read from the indexes instead of scanning all 41,988 tracks per click
- Noticeable improvement in startup and view-switching speed

---

## Planned

### Bridge expansion (next)
The Sonata Bridge is now in production. Future improvements that build on it:
- Music upload drag-and-drop into Sonata, writing to NAS via the bridge with optimistic local insertion
- Metadata editor: edit track tags from within Sonata, writes back to MP3 files via the bridge
- Cache-busting: version-stamp meta tag with localStorage comparison to force a fresh load when the deployed version differs from the cached one
- Cassette GIF background in the full-screen player

### Other
- RobLi Notes: hardcoded workplace variant served via Newton SharePoint
- Remote access for partner via the bridge (no longer needs Tailscale)
- Mobile app install documentation
- Film library companion app (TMDB integration, TV-friendly interface)
- A third Home button alongside Wheel of Fortune and Quickfire Playlist (idea TBC)
