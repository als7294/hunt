// Placeholder: replaced by the stream that owns this screen (docs/frontend-v2.md).
import { html, mount } from '../core.js';
import { page } from '../shell.js';
export function render(params) { mount(page('ask', html`<p>ask: ${JSON.stringify(params)}</p>`)); }
