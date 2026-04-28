# Sonata Changelog

Personal music player PWA. Streams from Jellyfin on NAS, served via GitHub Pages.

---

## v0.11.3 — 28 April 2026

### Artist Photography
- MusicBrainz query now uses unquoted, special-character-stripped lookup so "Beatles" finds "The Beatles", "AC/DC" doesn't break the Lucene parser, and so on
- Removed the User-Agent header from MusicBrainz fetch — browsers refuse to set it on `fetch()`, and trying to do so could cause requests to fail outright in some environments. This is the most likely root cause of the 0-out-of-3,021 result the previous Fetch All run produced
- Transient errors (HTTP 5xx, 429 rate-limit, network failures) no longer poison the cache as "no image". The result is only cached when it's a definitive answer (200 with no match, 404, or a real image URL). Anything else gets retried on the next pass
- New "Retry failed lookups" button in Settings, next to "Clear image cache". Clears only the null entries from both the MusicBrainz and fanart.tv caches, leaving any real hits in place. Designed for exactly the situation above: a previous Fetch All filled the cache with false negatives, and you want to re-attempt them without losing legitimate hits
- Console warnings logged for each transient failure during a fetch, so it's clear in DevTools whether MusicBrainz, fanart.tv, or the network is the culprit

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
- Sonata-Loading-Screen.html no longer needed as a separate file — the test card is embedded directly in the app

### Home View (new)
- Now the default landing screen, replacing All Tracks
- "Hello." header with live track and album counts
- Wheel of Fortune button: picks a random album and plays it from track 1
- 12 random album tiles ("Picked for you") drawn from albums, compilations and DJ mixes
- Reshuffle button refreshes the picks on demand
- Tiles also reshuffle automatically every time the user enters Home from another view
- Clicking a tile plays the album immediately and drills into it
- Home added as first item in both desktop sidebar and mobile bottom nav (replaces "Songs" tab on mobile)

### Performance
- Pre-built library indexes built once after fetch or cache load
- Indexes cover artists, albums, compilations, DJ mixes, albums-by-artist and tracks-by-album
- Album, Artist, Compilations and DJ Mixes views now read from the indexes instead of scanning all 41,988 tracks per click
- O(N²) `albumCategory()` calls eliminated
- Noticeable improvement in startup and view-switching speed

### UI
- "Personal Library" subtitle removed from sidebar
- Track row + button is now a properly bordered button, always visible at 85% opacity
- New + button in the desktop now-playing bar, right of the artist name
- New + button in the mobile mini-player, left of the prev/play/next controls
- All four + buttons (track row, full player, np-bar, mini-player) auto-disable when nothing is playing

### Settings
- New "Fetch All Artist Photos" button in the fanart.tv panel
- Walks every distinct album-artist at the existing 1/sec MusicBrainz rate limit
- Live progress display ("Fetching 47 / 312: Aphex Twin")
- Stop button to interrupt a long fetch run
- Skips artists already in the cache
- Final summary message shown for 8 seconds after completion

### Bugs Fixed
- Library cache now correctly invalidates indexes on reload (previously stale indexes could survive a refresh)

---

## v0.9 — 27 April 2026
- Fixed library cache failing silently for large libraries (41,000+ tracks)
- IndexedDB writes now batched in chunks of 2,000 tracks to avoid transaction size limits
- If cache save fails, meta key is removed so next load does a clean fetch rather than loading an empty cache
- Cache now correctly persists between sessions — library loads instantly after first fetch

---

## v0.8 — 26 April 2026
- Background library sync is now fully silent — no loading spinner, no re-render while browsing
- Sync runs 2 seconds after cache load, invisible to the user
- Only explicit Refresh or Connect & Load triggers visible loading

---

## v0.7 — 26 April 2026
### Jellyfin & Network
- Dual server URL: local network (fast) + Tailscale fallback (remote)
- Sonata tries local IP first with 2s timeout, silently falls back to Tailscale
- Library cache is now URL-agnostic — survives switching between local and Tailscale addresses
- Library cache survives code updates — no full reload needed when new version is deployed

### Album Pages
- Album artwork hero image at top of every album track list
- Album title, artist, year and track count displayed in hero
- Play button built into hero header
- Hero responsive — smaller on mobile

### Playlist Pages
- 2×2 artwork collage using real Jellyfin album art (Mondrian fallback)
- Play button added to playlist header

### Playlist Persistence
- Playlists shown immediately from localStorage on every open before any network call
- Jellyfin playlist sync runs in background and merges rather than replaces
- Local-only playlists (created offline) preserved alongside server playlists
- Every playlist change saved to localStorage as it happens

---

## v0.6 — 26 April 2026
### Architecture
- Jellyfin replaces local file picker entirely — no more folder/file selection
- Library fetched from Jellyfin API on load (tracks, metadata, artwork URLs, stream URLs)
- Audio playback streams directly from Jellyfin
- Playlists created, updated and deleted via Jellyfin API
- OPFS offline saving now fetches from Jellyfin stream URL
- jsmediatags library removed — tags come from Jellyfin

### Caching
- Library cached to IndexedDB after first load
- Subsequent opens load instantly from cache
- Background sync with Jellyfin after cache load
- Refresh button forces full re-fetch

### Navigation
- Artist pages now show album tiles (artwork, name, year) rather than flat track list
- Albums sorted chronologically by year within artist pages
- Artist hero (photo + name) shown at top of artist album grid
- Clicking album tile opens track list; Back returns to artist albums
- Search results show matching artist tiles first, then track/album results
- Clicking artist in search goes to their album grid

### Settings
- Jellyfin Connection section added: server URL + API key
- Credentials stored in localStorage, never in the HTML file

### Sonos
- Sonos bridge now passes Jellyfin stream URL directly to speakers
- Sonos pulls audio from NAS — phone is not in the audio chain

---

## v0.5 — April 2026
### Core Features
- Full playback controls: play, pause, skip, shuffle, repeat, volume
- Media Session API: lock screen and Apple Watch Now Playing controls
- Remote Playback API: AirPlay and Chromecast support
- Sonos bridge integration via Node.js server on NAS
- NAS connection manager: tries Tailscale first, falls back to QuickConnect

### Library & Navigation
- Songs, Artists, Albums, Genres, Compilations, DJ Mixes views
- Artists view: groups by Album Artist, filters Various Artists and single-track artists
- Albums view: proper artist albums only
- Compilations: albums where Album Artist is Various Artists / VA
- DJ Mixes: named DJ as Album Artist with 3+ distinct track artists
- All album drill-downs sort by track number
- Search across tracks, artists and albums
- Saved tracks view (OPFS offline)

### Skins
- Ten switchable skins: De Stijl, Noir, Scully, Vinyl, Blueprint, Tokyo Neon, Arctic, Terracotta, Forest, Rose Gold
- Scully palette derived from Peter's schnauzer: salt-and-pepper grey, purple collar, grass green, hotel cream
- Mondrian art generator adapts colours to each skin

### Artist Photography
- fanart.tv integration: artist photos fetched automatically while browsing
- MusicBrainz MBID lookup (rate-limited to 1/second) then fanart.tv image fetch
- Photos cached permanently in localStorage, fade in over Mondrian art
- API key field and cache clear button in Settings

### Offline & Storage
- OPFS offline track saving with progress overlay
- Save individual tracks or entire albums to device
- Saved tracks play without network connection

### PWA
- Installable on iPhone (Safari → Add to Home Screen) and Android (Chrome → Install)
- Runs full screen, no browser chrome
- Single self-contained HTML file
- Served via GitHub Pages (HTTPS)

### Bugs Fixed
- Missing renderGenreView function causing full JS crash on startup
- Broken single-quote inside template literal in playlist view

---

## Planned
- HTTPS / mixed content fix for artwork and audio on GitHub Pages
- Sonos bridge: full proxy that holds the Jellyfin API key on the NAS so devices and RobLi Notes don't ship credentials to the browser
- Cassette GIF background in the full-screen player
- Music upload drag-and-drop into Sonata, writing to NAS via the Sonos bridge with optimistic local insertion (depends on bridge being live)
- Metadata editor: edit track tags from within Sonata, writes back to MP3 files via Jellyfin
- Sonos bridge: Node.js server setup on NAS
- RobLi Notes: hardcoded workplace variant served via Newton SharePoint
- Remote access for partner (port forwarding or alternative to Tailscale)
- Mobile app install documentation
- Film library companion app (TMDB integration, TV-friendly interface)
