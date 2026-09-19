"""The panels under the canvas, as they are really built (C-1965).

The frame around a game is HTML (C-1956) and the game itself is canvas
(C-1959 .. C-1964), but the controls between them - the key settings, the
looks, the tuning, the copy button - are built by the page's own
JavaScript at load time. Reading the HTML does not show them, and grepping
the script for ``textContent=`` shows lines that may never run.

So this runs the page on a recording document: ``createElement`` returns a
node that remembers what was put in it, ``appendChild`` builds the tree,
and afterwards the tree is walked and every piece of text it holds is
reported. A panel that was never built has no text, and a judge reading
this can tell the two apart.
"""

from __future__ import annotations

from sidra_ai.creation.probekeys import KEY_EVENT_JS

PANEL_PROBE = KEY_EVENT_JS + """
const nothing = new Proxy(function(){}, {
  get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : nothing),
  apply: () => nothing, set: () => true });
const handlers = {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.performance = { now: () => 0 };
globalThis.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.Image = function(){ return nothing };
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
/* A node that remembers. Only what a reader would meet is kept: the text
   put into it, the label read out to a screen reader, and its children. */
function node(tag){
  const self = {
    tagName: String(tag || '').toUpperCase(), textContent: '', value: '',
    style: {}, dataset: {}, classList: { add(){}, remove(){}, toggle(){} },
    children: [], attrs: {},
    appendChild(child){ if (child && child.tagName !== undefined) self.children.push(child);
      return child },
    append(...kids){ kids.forEach(k => self.appendChild(k)); },
    insertBefore(child){ return self.appendChild(child) },
    removeChild(){}, remove(){}, focus(){}, blur(){}, click(){},
    setAttribute(name, value){ self.attrs[String(name)] = String(value) },
    getAttribute(name){ return self.attrs[String(name)] },
    removeAttribute(name){ delete self.attrs[String(name)] },
    addEventListener(type, fn){ (self.on = self.on || {}), (self.on[type] = fn) },
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 720, height: 320 }),
    getContext: () => nothing, width: 720, height: 320,
  };
  return self;
}
const root = node('main');
const canvas = node('canvas');
canvas.addEventListener = (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) };
globalThis.document = { readyState: 'complete', body: root,
  documentElement: node('html'),
  createElement: (tag) => node(tag),
  createTextNode: (text) => { const n = node('#text'); n.textContent = String(text); return n },
  querySelector: (sel) => (String(sel) === 'main' ? root : canvas),
  querySelectorAll: () => [],
  getElementById: () => canvas,
  addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn) } };
globalThis.requestAnimationFrame = () => 0;
SCRIPT_PLACEHOLDER
/* Anything that waited for the document says so now. */
(handlers.DOMContentLoaded || []).forEach(fn => { try { fn({}) } catch (e) {} });
(handlers.load || []).forEach(fn => { try { fn({}) } catch (e) {} });
function texts(n, out){
  if (!n) return out;
  if (n.textContent) out.push(String(n.textContent));
  for (const key of ['aria-label', 'title', 'placeholder']) {
    if (n.attrs && n.attrs[key]) out.push(String(n.attrs[key]));
  }
  (n.children || []).forEach(c => texts(c, out));
  return out;
}
console.log(JSON.stringify({ texts: texts(root, []),
  built: (root.children || []).length }));
"""


def panel_probe(script: str) -> str:
    """The page's own script, wrapped so its panels are really built."""

    return PANEL_PROBE.replace("SCRIPT_PLACEHOLDER", script)


__all__ = ["PANEL_PROBE", "panel_probe"]
