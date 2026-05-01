# Sonata Session Summary — April 30 2026

## What was completed today

### Bridge infrastructure
- node-fetch v2 installed on NAS to fix "fetch is not a function" errors in the `/mbid` route
- DSM reverse proxy timeouts increased to 1800 seconds (30 minutes) to allow large library fetches
- Library now loads successfully on desktop Chrome (41,988 tracks)

### Jellyfin remote access
- New port forwarding rule on EE Hub: external 8920 → internal 8920
- New DSM reverse proxy rule: JellyFin Direct, `petersonata.duckdns.org:8920` → `localhost:8096`
- Let's Encrypt certificate assigned to `petersonata.duckdns.org:8920` in DSM Security settings
- nginx reloaded to pick up certificate change (`sudo nginx -s reload`)
- Jellyfin password reset via Docker exec PIN method
- Jellyfin now accessible remotely at `https://petersonata.duckdns.org:8920`
- Working on: iPhone Jellyfin app, Apple Watch via Finy

### Network drives mapped
- Y: Music, M: movies, T: shows — all persistent via `net use /persistent:yes`

---

## What needs doing next session

### 1. Pagination fix for Sonata iPhone (highest priority)

Sonata currently fetches the entire library in one request (`Limit=100000`) which times out on mobile Safari. The fix is to paginate in batches of 5,000.

In `sonata-pwa.html`, find this block inside `fetchLibrary()`:

```javascript
const fields = 'AlbumArtist,Artists,Genres,ParentId,IndexNumber,RunTimeTicks,AlbumId,AlbumArtistIds,ProductionYear';
const data = await jfGet(
  `/Users/${jellyfin.userId}/Items?IncludeItemTypes=Audio&Recursive=true` +
  `&Fields=${fields}&SortBy=AlbumArtist,Album,IndexNumber,SortName` +
  `&SortOrder=Ascending&Limit=100000`
);

const items = data.Items || [];
```

Replace with:

```javascript
const fields = 'AlbumArtist,Artists,Genres,ParentId,IndexNumber,RunTimeTicks,AlbumId,AlbumArtistIds,ProductionYear';
const PAGE_SIZE = 5000;
let startIndex = 0;
let items = [];
let totalCount = null;

while (true) {
  const data = await jfGet(
    `/Users/${jellyfin.userId}/Items?IncludeItemTypes=Audio&Recursive=true` +
    `&Fields=${fields}&SortBy=AlbumArtist,Album,IndexNumber,SortName` +
    `&SortOrder=Ascending&Limit=${PAGE_SIZE}&StartIndex=${startIndex}`
  );
  const page = data.Items || [];
  if (totalCount === null) totalCount = data.TotalRecordCount || 0;
  items = items.concat(page);
  document.getElementById('loading-text').textContent = `Loading library… ${items.length.toLocaleString()} / ${totalCount.toLocaleString()}`;
  if (page.length < PAGE_SIZE) break;
  startIndex += PAGE_SIZE;
}
```

After making this change, redeploy `sonata-pwa.html` to GitHub Pages.

### 2. Artist photos — shared bridge cache

Currently each device crawls MusicBrainz and fanart.tv independently at 1 request/second, taking hours per device and producing no visible results (bug to investigate). The plan is to move the cache server-side:

- Add a new endpoint to `sonata-bridge.js`: `GET /artist-photo?artist=NAME`
- Bridge checks a local JSON cache file on the NAS first
- If not cached: does MusicBrainz MBID lookup + fanart.tv image fetch, stores result
- Returns `{ url }` to the browser
- Browser caches the URL in localStorage as before
- Result: crawl happens once across all devices, phone gets photos instantly without its own crawl

Also investigate why photos fetched on desktop Chrome did not appear — the fetch completed (5049 artists, ~85 mins) but no images rendered. Likely a bug in how Sonata reads the cache back and injects photos into artist cards.

### 3. Architecture review

The current setup feels scattered. Things to think through and rationalise:

- Where does the source of truth live for each type of data (library, photos, playlists, settings)
- Library caching strategy: IndexedDB on device vs served from bridge
- Artist name inconsistencies causing duplicate entries (e.g. Beatles vs The Beatles)
- Whether the bridge should do more heavy lifting so Sonata stays thin

### 4. Fuzzy artist matching

A script called `fuzzy_artist_match.py` was built in a previous session and parked. It normalises artist tag inconsistencies in the music library. This should be run before the photo cache work so photo lookups use clean, consistent names. Check local files from the previous session — if not found, rewrite from scratch.

---

## Key addresses and credentials

| Item | Value |
|---|---|
| NAS local | `192.168.1.83` |
| DSM | `http://192.168.1.83:5000` |
| Bridge | `https://petersonata.duckdns.org:5443` |
| Jellyfin local | `http://192.168.1.83:8096` |
| Jellyfin remote | `https://petersonata.duckdns.org:8920` |
| Sonata | `https://petersonata.github.io/Sonata/sonata-pwa.html` |
| NAS SSH | `ssh "Peter Admin@192.168.1.83"` |
| Bridge file | `/volume1/sonata-bridge/sonata-bridge.js` |
| Sonata package | `C:\Users\peter\OneDrive\Documents\sonata-package\` |
| EE Hub | `192.168.1.254` |
| NAS username | `Peter Admin` |
| Music share | `Y:\` (`\\192.168.1.83\Music`) |
| Movies share | `M:\` (`\\192.168.1.83\movies`) |
| Shows share | `T:\` (`\\192.168.1.83\shows`) |

## Useful commands

### Restart nginx on NAS
```
sudo nginx -s reload
```

### Check bridge logs
```
sudo /usr/local/bin/pm2 logs sonata-bridge --lines 20 --nostream
```

### Restart bridge
```
sudo /usr/local/bin/pm2 restart sonata-bridge --cwd /volume1/sonata-bridge
```

### Map network drives (after reboot)
```
net use Y: \\192.168.1.83\Music "YourPassword" /user:"Peter Admin" /persistent:yes
net use M: \\192.168.1.83\movies "YourPassword" /user:"Peter Admin" /persistent:yes
net use T: \\192.168.1.83\shows "YourPassword" /user:"Peter Admin" /persistent:yes
```

### Reset Jellyfin password via Docker
```
docker exec jellyfin-jellyfin-1-1 cat /config/passwordreset[filename shown in app]
```
