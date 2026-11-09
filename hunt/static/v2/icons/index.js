// The vendored icons (docs/frontend-v2.md): Lucide (ISC) here, Simple Icons (CC0) in brand/. The CSP keeps every image
// on this origin, so a new icon is copied in, not linked. Drawn as a mask, so an icon takes the colour of its text.
import { raw } from '../core.js';

export const BRANDS = new Set(['bluesky','deviantart','discord','facebook','flickr','github','gitlab','goodreads','google','googlemaps','gravatar','imdb','instagram','keybase','kick','letterboxd','linkedin','linktree','mastodon','medium','patreon','pinterest','reddit','snapchat','soundcloud','spotify','stackexchange','stackoverflow','steam','strava','substack','telegram','threads','tiktok','tumblr','twitch','untappd','venmo','wikipedia','x','youtube']);
const ALIAS = { twitter: 'x' };
const draw = (path, size, opacity, color) => raw(`<span aria-hidden="true" style="display:block;flex:none;width:${+size}px;height:${+size}px;opacity:${+opacity};background:${color};-webkit-mask:url(/v2/icons/${path}.svg) center/contain no-repeat;mask:url(/v2/icons/${path}.svg) center/contain no-repeat"></span>`);
const safe = c => /^(#[0-9a-f]{3,8}|currentColor|var\(--[\w-]+\))$/i.test(c) ? c : 'currentColor';

// icon('search'), icon('mail', { size: 13, opacity: .5, color: 'var(--hunt)' }): a Lucide name
export const icon = (name, { size = 16, opacity = 1, color = 'currentColor' } = {}) => draw(String(name).replace(/[^a-z0-9-]/g, ''), size, opacity, safe(color));
// brand('Stack Exchange'): a site's logo by its name as Hunt writes it; a site with no logo here gets a globe
export const brand = (site, { size = 16, opacity = 1, color = 'currentColor' } = {}) => {
  const key = String(site ?? '').toLowerCase().replace(/[^a-z0-9]/g, ''), slug = ALIAS[key] || key;
  return BRANDS.has(slug) ? draw(`brand/${slug}`, size, opacity, safe(color)) : icon('globe', { size, opacity, color });
};
