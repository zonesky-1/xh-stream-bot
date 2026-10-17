// Jalankan decoder juicycodes asli dari player.js — ambil config stream
// Pemakaian: node run_juicy.js <embed_url>
const https = require("https");
const http = require("http");

function fetchBuf(url, headers = {}) {
  return new Promise((res, rej) => {
    const u = new URL(url);
    const lib = u.protocol === "https:" ? https : http;
    const req = lib.get(url, { headers: { "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
      ...headers } }, (r) => {
      if (r.statusCode >= 300 && r.statusCode < 400 && r.headers.location) {
        return res(fetchBuf(new URL(r.headers.location, url).href, headers));
      }
      const chunks = [];
      r.on("data", (c) => chunks.push(c));
      r.on("end", () => res({ status: r.statusCode, body:
        Buffer.concat(chunks).toString("utf8") }));
    });
    req.on("error", rej); req.setTimeout(45000, () => req.destroy(new Error("timeout")));
  });
}

(async () => {
  const embedUrl = process.argv[2];
  if (!embedUrl) { console.error("usage: node run_juicy.js <embed_url>"); process.exit(2); }
  const emb = await fetchBuf(embedUrl);
  const html = emb.body;
  // payload: _juicycodes("a"+"b"+...)
  const m = html.match(/_juicycodes\(([\s\S]*?)\);/);
  if (!m) { console.error("ERR payload nggak ketemu"); process.exit(1); }
  // player.js: host dari embed
  const host = new URL(embedUrl).origin;
  const pj = await fetchBuf(host + "/assets/players/videojs/player.js",
                            { Referer: embedUrl });
  if (pj.status !== 200) { console.error("ERR player.js", pj.status); process.exit(1); }

  // shim lingkungan — videojs = proxy serba-bisa (player.js register komponen)
  const mkStub = () => new Proxy(function(){}, {
    get: (t, p) => {
      if (p === Symbol.toPrimitive) return () => "stub";
      if (p === "length") return 0;
      if (p === Symbol.iterator) return function*(){};
      return mkStub();
    },
    apply: () => mkStub(),
    construct: () => mkStub(),
    set: () => true,
  });
  const sandbox = {
    window: {}, document: { currentScript: null, addEventListener(){}, querySelector(){return null},
                             createElement(){ return { style:{}, setAttribute(){}, appendChild(){} }; },
                             documentElement: { style: {} }, head: { appendChild(){} }, body:{appendChild(){}} },
    navigator: { userAgent: "Mozilla/5.0", language: "en-US" },
    location: new URL(embedUrl),
    localStorage: { getItem: () => null, setItem(){}, removeItem(){} },
    sessionStorage: { getItem: () => null, setItem(){} },
    console, setTimeout, clearTimeout, setInterval, clearInterval,
    videojs: mkStub(),
  };
  sandbox.window = sandbox; sandbox.globalThis = sandbox;
  const vm = require("vm");
  const ctx = vm.createContext(sandbox);
  try {
    vm.runInContext(pj.body, ctx, { filename: "player.js", timeout: 15000 });
  } catch (e) {
    console.error("player.js load warn:", String(e).slice(0, 200));
  }
  const fn = sandbox._juicycodes || (sandbox.window && sandbox.window._juicycodes);
  if (!fn) { console.error("ERR _juicycodes nggak ter-expose"); process.exit(1); }
  // eval ekspresi string payload
  const payload = vm.runInContext("(" + m[1] + ")", ctx, { timeout: 5000 });
  const out = fn(payload);
  console.log(typeof out === "string" ? out : JSON.stringify(out));
})().catch((e) => { console.error("FATAL", String(e).slice(0, 300)); process.exit(1); });
