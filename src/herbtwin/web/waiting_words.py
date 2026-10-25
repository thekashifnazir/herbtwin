"""What a wait shows while it works, as Claude Code shows its own (24 Oct, Kash: "Can't you do
wait times like you do for Claude from when it starts but plant related … that would be nice
to help as people wait"): a pulsing dot, a plant word that changes every few seconds and the
seconds since it started, then what is really happening after a dot ("searching trusted
pages with Tavily"). This brings the running count back on purpose: 21 Oct had none.

One script, written here once: base.html carries it for the answer pages, the photo wait page
(progress.py) carries it too. A screen reader hears only the real status, never the words or
the count (aria-hidden)."""

from __future__ import annotations

import json

WORDS = (
    "Germinating",
    "Taking root",
    "Sprouting",
    "Unfurling",
    "Photosynthesising",
    "Pollinating",
    "Mulching",
    "Potting on",
)
EVERY_S = 4  # a new word this often

# herbtwinWait(el, marks, o): el's text becomes the moving line until the returned stop() is
# called. marks: [[seconds, status], ...], the status after the dot from that second on; a
# status may be a function, read when its mark is reached. stop.say(text) sets the status
# now (a search starting). o.label: an aria-label kept while it runs (a button). o.from: when
# the wait began (default now).
WAIT_JS = (
    "window.herbtwinWait=(el,marks=[],o={})=>{"
    f"const W={json.dumps(WORDS)},t=o.from||Date.now();let n=0;"
    'const fun=document.createElement("span"),real=document.createElement("span");'
    'fun.className="wait-fun";fun.setAttribute("aria-hidden","true");real.className="wait-real";'
    'el.textContent="";el.append(fun,real);el.classList.add("waiting");'
    'if(o.label)el.setAttribute("aria-label",o.label);'
    'const say=x=>{real.textContent=x?" · "+x:""};'
    "const show=()=>{const s=Math.floor((Date.now()-t)/1e3);"
    'while(n<marks.length&&s>=marks[n][0]){const m=marks[n][1];say(typeof m==="function"?m():m);n++}'
    f'fun.textContent=W[Math.floor(s/{EVERY_S})%W.length]+"… "+s+"s"}};'
    "show();const i=setInterval(show,1000);"
    'const stop=()=>{clearInterval(i);el.classList.remove("waiting");'
    'if(o.label)el.removeAttribute("aria-label");fun.remove();real.remove()};'
    "stop.say=say;return stop};"
)
