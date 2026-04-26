# Sonata Changelog

Personal music player PWA. Streams from Jellyfin on NAS, served via GitHub Pages.

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
- Metadata editor: edit track tags from within Sonata, writes back to MP3 files via Jellyfin
- Sonos bridge: Node.js server setup on NAS
- RobLi Notes: hardcoded workplace variant served via Newton SharePoint
- Remote access for partner (port forwarding or alternative to Tailscale)
- Mobile app install documentation
- Film library companion app (TMDB integration, TV-friendly interface)
