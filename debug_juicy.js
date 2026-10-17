// Debug decoder juicycodes: payload type + out
const https = require("https"), vm = require("vm");
function fetchBuf(url, headers = {}) {
  return new Promise((res, rej) => {
    const req = https.get(url, { headers: { "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
      ...headers } }, (r) => {
      if (r.statusCode >= 300 && r.statusCode < 400 && r.headers.location)
        return res(fetchBuf(new URL(r.headers.location, url).href, headers));
      const c = []; r.on("data", d => c.push(d));
      r.on("end", () => res({ status: r.statusCode, body: Buffer.concat(c).toString("utf8") }));
    });
    req.on("error", rej); req.setTimeout(45000, () => req.destroy(new Error("timeout")));
  });
}
const mkStub = () => new Proxy(function(){}, {
  get: (t, p) => { if (p === Symbol.toPrimitive) return () => "stub";
    if (p === "length") return 0; if (p === Symbol.iterator) return function*(){};
    return mkStub(); },
  apply: () => mkStub(), construct: () => mkStub(), set: () => true });

(async () => {
  const embedUrl = process.argv[2] || "https://barplay.xyz/embed/YNmI2zkq6a51BQO";
  let html;
  if (process.argv[3]) {
    // HTML dari file (di-fetch pemanggil, agar cookie session bisa dipakai ulang)
    html = require("fs").readFileSync(process.argv[3], "utf8");
  } else {
    html = (await fetchBuf(embedUrl)).body;
  }
  const m = html.match(/_juicycodes\(([\s\S]*?)\);/);
  if (!m) { console.log("ERR payload nggak ketemu"); return; }
  const host = new URL(embedUrl).origin;
  const pj = await fetchBuf(host + "/assets/players/videojs/player.js", { Referer: embedUrl });
  const sandbox = { window: {}, document: { currentScript:null, addEventListener(){}, querySelector(){return null},
      createElement(){ return {style:{}, setAttribute(){}, appendChild(){}}; },
      documentElement:{style:{}}, head:{appendChild(){}}, body:{appendChild(){}} },
    navigator: { userAgent: "Mozilla/5.0", language: "en-US" },
    location: new URL(embedUrl),
    localStorage: { getItem: () => null, setItem(){}, removeItem(){} },
    sessionStorage: { getItem: () => null, setItem(){} },
    console, setTimeout, clearTimeout, setInterval, clearInterval, videojs: mkStub() };
  // TANGKAP eval — init() memang sengaja void, hasil decode di-eval di akhir
  let captured = null;
  sandbox.eval = (code) => { captured = String(code); return undefined; };
  sandbox.window = sandbox; sandbox.globalThis = sandbox;
  const ctx = vm.createContext(sandbox);
  try {
    vm.runInContext(pj.body, ctx, { filename: "player.js", timeout: 15000 });
  } catch (e) { console.log("load warn:", String(e).slice(0, 200)); }
  const payload = vm.runInContext("(" + m[1] + ")", ctx, { timeout: 5000 });
  console.log("payload:", typeof payload, "len:", payload && payload.length);
  console.log("head:", String(payload).slice(0, 80));
  const fn = sandbox._juicycodes;
  console.log("fn:", typeof fn);
  if (typeof fn !== "function") return;
  try {
    const out = fn(payload);
    // ambil m3u8 + poster dari config yang terekap
    const src = captured && captured.match(/"src":"(https:[^"]+\.m3u8)"/);
    const poster = captured && captured.match(/"poster":"(https:[^"]+)"/);
    if (src) {
      if (poster) console.log("POSTER " + poster[1].replace(/\\\//g, "/"));
      console.log(src[1].replace(/\\\//g, "/"));
    } else { console.log("ERR nggak ada m3u8; captured head:");
           console.log(String(captured).slice(0, 300)); }
  } catch (e) { console.log("call ERR:", String(e).slice(0, 300)); }
})().catch(e => console.log("FATAL", String(e).slice(0, 300)));
