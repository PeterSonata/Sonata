/**
 * Photo store: image bytes on disk.
 *
 * The store.json index (handled by lib/store.js) holds the metadata for each
 * artist's photos. This module owns the actual image files. They live at
 * /volume1/sonata-bridge/data/photos/, keyed by MBID, so they sit under data/
 * which is already gitignored. Hundreds of megabytes of artist art has no
 * business in version control.
 *
 * Same atomic discipline as the JSON store: bytes go to a temp file then get
 * renamed over the final name, so an interrupted download can never leave a
 * half-written image that later reads as corrupt.
 *
 * The directory is resolved relative to this file, not the working directory,
 * so it lands in the right place regardless of how PM2 launched the process.
 */

const fs = require('fs');
const fsp = fs.promises;
const path = require('path');

const PHOTO_DIR = path.join(__dirname, '..', 'data', 'photos');

// A filename is only ever {mbid}-{kind}.{ext}. Guard the served route against
// path traversal by allowing nothing but that exact shape.
const SAFE_NAME = /^[0-9a-f-]{30,40}-(thumb|bg)\.(jpg|jpeg|png|webp)$/i;

function isSafeName(name) {
  return typeof name === 'string' && SAFE_NAME.test(name);
}

function dir() {
  return PHOTO_DIR;
}

function fullPath(name) {
  return path.join(PHOTO_DIR, name);
}

// True if the image file already exists on disk.
async function exists(name) {
  try {
    await fsp.access(fullPath(name));
    return true;
  } catch {
    return false;
  }
}

// Write bytes atomically. Returns the bare filename written.
async function write(name, buffer) {
  await fsp.mkdir(PHOTO_DIR, { recursive: true });
  const tmp = fullPath(`${name}.tmp`);
  await fsp.writeFile(tmp, buffer);
  await fsp.rename(tmp, fullPath(name));
  return name;
}

// Pick a file extension from a URL or content-type, defaulting to jpg.
function extFor(url, contentType) {
  const ct = (contentType || '').toLowerCase();
  if (ct.includes('png')) return 'png';
  if (ct.includes('webp')) return 'webp';
  if (ct.includes('jpeg') || ct.includes('jpg')) return 'jpg';
  const m = (url || '').toLowerCase().match(/\.(jpg|jpeg|png|webp)(\?|$)/);
  if (m) return m[1] === 'jpeg' ? 'jpg' : m[1];
  return 'jpg';
}

module.exports = { dir, fullPath, isSafeName, exists, write, extFor, PHOTO_DIR };
