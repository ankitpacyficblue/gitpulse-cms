"""The embed script and the readable post page. Text goes in with textContent only, never innerHTML."""
from html import escape

SCRIPT = r"""(function () {
  var me = document.currentScript;
  var api = new URL("posts", me.src).href;
  var box = document.querySelector("[data-gitpulse]");
  if (!box) { box = document.createElement("div"); me.parentNode.insertBefore(box, me); }
  var fixed = me.getAttribute("data-post");

  function el(tag, text) { var n = document.createElement(tag); if (text) n.textContent = text; return n; }
  function image(url, alt) { var n = el("img"); n.src = url; n.alt = alt || ""; n.style.maxWidth = "100%"; return n; }
  function inline(node, text) {
    var re = /(!?)\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)|\*\*([^*]+)\*\*/g, at = 0, m;
    while ((m = re.exec(text))) {
      node.append(text.slice(at, m.index));
      if (m[4]) node.append(el("strong", m[4]));
      else if (m[1]) node.append(image(m[3], m[2]));
      else { var a = el("a", m[2]); a.href = m[3]; node.append(a); }
      at = re.lastIndex;
    }
    node.append(text.slice(at));
    return node;
  }
  function markdown(text) {
    var out = el("div"), list = null, para = [];
    function flush() { if (para.length) out.append(inline(el("p"), para.join(" "))); para = []; }
    String(text).split(/\r?\n/).forEach(function (line) {
      var h = line.match(/^(#{1,6})\s+(.*)/), item = line.match(/^\s*([-*]|\d+\.)\s+(.*)/);
      if (item) {
        flush();
        var kind = /\d/.test(item[1]) ? "OL" : "UL";
        if (!list || list.tagName !== kind) out.append(list = el(kind));
        list.append(inline(el("li"), item[2]));
        return;
      }
      list = null;
      if (h) { flush(); out.append(inline(el("h" + Math.min(h[1].length + 1, 6)), h[2])); }
      else if (!line.trim()) flush();
      else para.push(line.trim());
    });
    flush();
    return out;
  }
  function get(url) { return fetch(url).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  function fail() { box.textContent = "Posts are not available right now."; }

  function showPost(slug) {
    get(api + "/" + encodeURIComponent(slug)).then(function (p) {
      var parts = [el("h1", p.title), markdown(p.content_markdown)];
      if (!fixed) { var back = el("a", "All posts"); back.href = "#"; parts.unshift(back); }
      box.replaceChildren.apply(box, parts);
    }).catch(fail);
  }
  function showList() {
    get(api).then(function (data) {
      box.replaceChildren.apply(box, data.posts.map(function (p) {
        var card = el("article"), title = el("h2"), link = el("a", p.title);
        link.href = "#post=" + p.slug;
        title.append(link);
        if (p.cover_image) card.append(image(p.cover_image.url, p.cover_image.alt));
        card.append(title, el("p", p.excerpt));
        return card;
      }));
    }).catch(fail);
  }
  function show() {
    var m = location.hash.match(/^#post=([\w-]+)$/);
    if (fixed) showPost(fixed); else if (m) showPost(m[1]); else showList();
  }
  if (!fixed) window.addEventListener("hashchange", show);
  show();
})();
"""


def post_page(title: str, description: str, slug: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>'
            f'<meta name="description" content="{escape(description or "")}">'
            f'<style>body{{font:17px/1.6 system-ui,sans-serif;max-width:42rem;margin:2rem auto;padding:0 16px}}</style>'
            f'</head><body><div data-gitpulse></div>'
            f'<script src="../../embed.js" data-post="{escape(slug)}"></script></body></html>')
