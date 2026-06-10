// lib/sonos.js
// ============================================================
// Sonos control for the Sonata bridge.
//
// Two halves:
//   1. Discovery. SSDP multicast to find Sonos players on the
//      LAN. Falls back to a configured list of IPs from .env
//      (SONOS_HOSTS) so a speaker is always reachable even when
//      multicast is blocked (Docker bridge networking, VLANs).
//   2. Control. SOAP calls to a player's AVTransport and
//      RenderingControl services: set URI, play, pause, next,
//      previous, volume, plus a transport-state read used by the
//      push-on-advance handler to know when a track has ended.
//
// No external deps. Uses Node 20 native fetch for SOAP POSTs and
// the built-in dgram for SSDP. Mirrors the rest of the bridge:
// native fetch only, no node-fetch.
// ============================================================


// Fetch the whole Sonos household topology from any one reachable player.
// All players share the same topology, so a single call describes everything.
// Returns visible, addressable zones only: stereo-pair satellites and bonded
// units (Invisible="1") are dropped, and each zone resolves to its group
// coordinator's host, the unit that accepts transport and drives the pair/group.
async function getZones(seedHost) {
  const body =
    '<?xml version="1.0"?>' +
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" ' +
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>' +
    '<u:GetZoneGroupState xmlns:u="urn:schemas-upnp-org:service:ZoneGroupTopology:1">' +
    '</u:GetZoneGroupState></s:Body></s:Envelope>';

  const res = await fetch(`http://${seedHost}:1400/ZoneGroupTopology/Control`, {
    method: 'POST',
    headers: {
      'Content-Type': 'text/xml; charset="utf-8"',
      SOAPACTION: '"urn:schemas-upnp-org:service:ZoneGroupTopology:1#GetZoneGroupState"',
    },
    body,
  });
  if (!res.ok) throw new Error(`ZoneGroupTopology ${res.status}`);

  // State arrives XML-escaped inside the SOAP response. Unescape, then pull
  // members and groups out by hand.
  const xml = unescapeXml(await res.text());

  // UUID -> { host, name } for every visible member.
  const members = {};
  for (const m of xml.matchAll(/<ZoneGroupMember\s([^>]*?)\/?>/g)) {
    const a = m[1];
    const uuid = (a.match(/UUID="([^"]*)"/) || [])[1];
    const name = unescapeXml((a.match(/ZoneName="([^"]*)"/) || [])[1] || '');
    const loc = (a.match(/Location="([^"]*)"/) || [])[1] || '';
    const host = (loc.match(/^https?:\/\/([^:/]+)/) || [])[1];
    if (!uuid || !host || /Invisible="1"/.test(a)) continue;
    members[uuid] = { host, name };
  }

  // One entry per zone group, addressed at its coordinator.
  const zones = [];
  for (const g of xml.matchAll(/<ZoneGroup\s([^>]*?)>/g)) {
    const coord = (g[1].match(/Coordinator="([^"]*)"/) || [])[1];
    if (members[coord]) zones.push(members[coord]);
  }
  return zones;
}

function unescapeXml(s) {
  return s
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&'); // ampersand last
}

const dgram = require('dgram');

// Sonos players speak UPnP on port 1400.
const SONOS_PORT = 1400;

// SSDP multicast endpoint.
const SSDP_ADDR = '239.255.255.250';
const SSDP_PORT = 1900;

// The search target that Sonos ZonePlayers respond to.
const SONOS_ST = 'urn:schemas-upnp-org:device:ZonePlayer:1';

// ------------------------------------------------------------
// Discovery
// ------------------------------------------------------------

// Read the manual fallback list from the environment. Comma
// separated IPs, e.g. SONOS_HOSTS=192.168.1.40,192.168.1.41.
// These are always merged into discovery results so a known
// speaker survives a multicast failure.
function configuredHosts() {
  const raw = process.env.SONOS_HOSTS || '';
  return raw
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
}

// Fire an SSDP M-SEARCH and collect responding Sonos players for
// `timeoutMs`. Resolves to an array of { host } objects. Always
// merges in the configured fallback hosts, deduplicated by host.
function discover(timeoutMs = 3000) {
  return new Promise((resolve) => {
    const found = new Map(); // host -> { host }

    // Seed with the manual fallback list up front, so even a total
    // multicast failure still returns the known speakers.
    for (const host of configuredHosts()) {
      found.set(host, { host });
    }

    let socket;
    try {
      socket = dgram.createSocket({ type: 'udp4', reuseAddr: true });
    } catch (err) {
      // If we cannot even open a socket, return the fallback list.
      return resolve([...found.values()]);
    }

    const done = () => {
      try { socket.close(); } catch (_) { /* already closed */ }
      resolve([...found.values()]);
    };

    socket.on('error', () => done());

    socket.on('message', (msg, rinfo) => {
      const text = msg.toString();
      // Only count replies that look like a Sonos ZonePlayer.
      if (text.includes('Sonos') || text.includes(SONOS_ST)) {
        if (!found.has(rinfo.address)) {
          found.set(rinfo.address, { host: rinfo.address });
        }
      }
    });

    const search = Buffer.from(
      'M-SEARCH * HTTP/1.1\r\n' +
      `HOST: ${SSDP_ADDR}:${SSDP_PORT}\r\n` +
      'MAN: "ssdp:discover"\r\n' +
      'MX: 1\r\n' +
      `ST: ${SONOS_ST}\r\n\r\n`
    );

    socket.bind(() => {
      try {
        socket.send(search, 0, search.length, SSDP_PORT, SSDP_ADDR);
      } catch (_) {
        // Send failed (multicast blocked). Fallback list still returns.
      }
    });

    setTimeout(done, timeoutMs);
  });
}

// ------------------------------------------------------------
// Room-name lookup
// ------------------------------------------------------------

// Fetch a player's device description and read its <roomName>, so
// the desktop picker can show "Library" rather than a bare IP. One
// extra HTTP GET per host. Returns null on any failure (not a
// Sonos, powered off, slow) so a bad host never sinks the listing.
async function roomName(host, timeoutMs = 1500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(
      `http://${host}:${SONOS_PORT}/xml/device_description.xml`,
      { signal: controller.signal }
    );
    if (!res.ok) return null;
    const xml = await res.text();
    const m = xml.match(/<roomName>([^<]*)<\/roomName>/);
    return m ? m[1] : null;
  } catch (_) {
    return null; // unreachable or not a Sonos
  } finally {
    clearTimeout(timer);
  }
}

// Enrich a list of { host } players with a name, resolving all
// hosts in parallel so listing N speakers costs one round-trip of
// latency, not N. Hosts that do not answer keep name: null, which
// the client can fall back to showing as the bare IP.
async function withRoomNames(players) {
  return Promise.all(
    players.map(async (pl) => ({
      ...pl,
      name: await roomName(pl.host),
    }))
  );
}

// ------------------------------------------------------------
// SOAP control
// ------------------------------------------------------------

// Map of service shortname to its UPnP control URL and service type.
const SERVICES = {
  transport: {
    path: '/MediaRenderer/AVTransport/Control',
    type: 'urn:schemas-upnp-org:service:AVTransport:1',
  },
  rendering: {
    path: '/MediaRenderer/RenderingControl/Control',
    type: 'urn:schemas-upnp-org:service:RenderingControl:1',
  },
};

// XML-escape a value going into a SOAP body. Track URLs can carry
// ampersands and query strings, which would break the envelope.
function xmlEscape(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

// Build and POST a SOAP envelope to a player's service. `args` is
// an ordered array of [name, value] pairs, since SOAP arguments are
// position-sensitive. Returns the raw response body text.
async function soap(host, service, action, args = []) {
  const svc = SERVICES[service];
  if (!svc) throw new Error(`unknown service: ${service}`);

  const body = args
    .map(([name, val]) => `<${name}>${xmlEscape(val)}</${name}>`)
    .join('');

  const envelope =
    '<?xml version="1.0" encoding="utf-8"?>' +
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" ' +
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">' +
    '<s:Body>' +
    `<u:${action} xmlns:u="${svc.type}">${body}</u:${action}>` +
    '</s:Body></s:Envelope>';

  const res = await fetch(`http://${host}:${SONOS_PORT}${svc.path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'text/xml; charset="utf-8"',
      // SOAPACTION must be the service type and action, quoted.
      SOAPACTION: `"${svc.type}#${action}"`,
    },
    body: envelope,
  });

  const text = await res.text();
  if (!res.ok) {
    // Sonos returns a SOAP fault with a UPnP errorCode inside.
    const codeMatch = text.match(/<errorCode>(\d+)<\/errorCode>/);
    const code = codeMatch ? codeMatch[1] : res.status;
    throw new Error(`Sonos ${action} failed on ${host}: UPnP ${code}`);
  }
  return text;
}

// All transport actions target instance 0 (the only instance on a
// standalone player).
const INSTANCE = ['InstanceID', '0'];

// Point the player at a stream URL and start it. The metadata arg
// is left empty: Sonos will play a bare URI without DIDL-Lite, and
// building valid DIDL is more trouble than it earns for our use.
async function setUri(host, uri) {
  await soap(host, 'transport', 'SetAVTransportURI', [
    INSTANCE,
    ['CurrentURI', uri],
    ['CurrentURIMetaData', ''],
  ]);
}

async function play(host) {
  await soap(host, 'transport', 'Play', [INSTANCE, ['Speed', '1']]);
}

async function pause(host) {
  await soap(host, 'transport', 'Pause', [INSTANCE]);
}

async function next(host) {
  await soap(host, 'transport', 'Next', [INSTANCE]);
}

async function previous(host) {
  await soap(host, 'transport', 'Previous', [INSTANCE]);
}

// Volume is 0 to 100 on the Master channel.
async function setVolume(host, level) {
  const clamped = Math.max(0, Math.min(100, parseInt(level, 10) || 0));
  await soap(host, 'rendering', 'SetVolume', [
    INSTANCE,
    ['Channel', 'Master'],
    ['DesiredVolume', clamped],
  ]);
}

// Read transport state: PLAYING, PAUSED_PLAYBACK, STOPPED,
// TRANSITIONING. Used by the push-on-advance handler to detect a
// finished track (state goes to STOPPED with nothing queued).
async function getTransportState(host) {
  const text = await soap(host, 'transport', 'GetTransportInfo', [INSTANCE]);
  const m = text.match(/<CurrentTransportState>([^<]+)<\/CurrentTransportState>/);
  return m ? m[1] : 'UNKNOWN';
}

module.exports = {
  discover,
  configuredHosts,
  roomName,
  withRoomNames,
  getZones,  
  setUri,
  play,
  pause,
  next,
  previous,
  setVolume,
  getTransportState,
};
