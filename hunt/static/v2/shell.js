// The floating pill nav every screen sits under (the design's lines 12–21). Owned by the shell stream in docs/frontend-v2.md.
import { html } from './core.js';
const NAV = [['#/', 'Search', 'ask'], ['#/history', 'History', 'history'], ['#/vault', 'Vault', 'vault']];
export const page = (now, content) => html`<div style="min-height:100vh;display:flex;flex-direction:column;align-items:center;gap:24px;padding:14px 16px 40px;animation:hPage .35s ease">
  <nav style="display:flex;gap:6px;align-items:center;padding:6px 8px;border-radius:999px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.12)">
    <b style="padding:0 12px">hunt</b>${NAV.map(([href, label, k]) => html`<a href="${href}" style="padding:8px 14px;border-radius:999px;text-decoration:none;color:var(--ink);${k === now ? 'background:#f2f2f7' : ''}">${label}</a>`)}
    <a href="/" style="padding:8px 14px;color:var(--ink-2);text-decoration:none" title="The current app, until every screen has moved here">Classic</a>
  </nav>${content}</div>`;
