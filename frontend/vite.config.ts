import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

// The dev server proxies to the backend so the browser only ever sees one
// origin -- the same arrangement production gets for free, where FastAPI
// serves the built SPA itself. VITE_API_TARGET exists because under Docker
// Compose the backend is another container ("http://api:8000"), not localhost.
const target = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

/**
 * The absolute origin this build will be served from.
 *
 * Canonical URLs, Open Graph tags and the sitemap are all absolute by
 * specification, so a build has to be told where it is going. Getting this
 * wrong is worse than omitting it -- a canonical pointing at the wrong origin
 * tells search engines to index someone else's page -- so it is a build-time
 * variable with a loud default rather than a runtime guess.
 */
const SITE_URL = (process.env.VITE_SITE_URL ?? "https://algostudio-wu5c.onrender.com")
  .replace(/\/+$/, "");

/**
 * Every page, in one place.
 *
 * The sitemap, the robots file and the server's route table are all generated
 * from this list, which is the only way they stay in agreement. `url` is the
 * clean path the server serves the file at; `null` means "reachable, but not a
 * destination" (the 404 body).
 */
interface Page {
  file: string;
  url: string | null;
  priority?: string;
  changefreq?: string;
  /** Inline this page's CSS into the HTML: one request, no blocking fetch. */
  inlineCss?: boolean;
}

const PAGES: Page[] = [
  { file: "index.html",   url: "/",        priority: "1.0", changefreq: "monthly", inlineCss: true },
  { file: "app.html",     url: "/app",     priority: "0.9", changefreq: "monthly" },
  { file: "faq.html",     url: "/faq",     priority: "0.6", changefreq: "monthly", inlineCss: true },
  { file: "privacy.html", url: "/privacy", priority: "0.3", changefreq: "yearly",  inlineCss: true },
  { file: "terms.html",   url: "/terms",   priority: "0.3", changefreq: "yearly",  inlineCss: true },
  { file: "404.html",     url: null,                                                inlineCss: true },
];

/**
 * A consent gate for analytics that actually stores something.
 *
 * Emitted only when VITE_ANALYTICS_CONSENT=1, so the default build contains
 * none of it. Deliberately a plain inline snippet rather than a component:
 * the content pages ship no JavaScript, and pulling in a framework to ask one
 * question would cost more than the thing being measured.
 *
 * The rules it has to obey to be worth anything: nothing loads before a yes,
 * declining is one click and is remembered, and the choice can be changed
 * afterwards. A banner whose only button is "Accept" is not consent.
 */
function consentSnippet(src: string, domain: string): string {
  const attrs = domain ? ` s.setAttribute('data-domain',${JSON.stringify(domain)});` : "";
  return `<style>
.cc-bar{position:fixed;left:0;right:0;bottom:0;z-index:999;display:flex;gap:14px;
align-items:center;flex-wrap:wrap;justify-content:center;padding:14px 18px;
background:#12181f;border-top:1px solid #232c38;color:#c2ccd8;
font:15px/1.5 Inter,"Segoe UI",system-ui,sans-serif}
.cc-bar p{margin:0;max-width:46rem}
.cc-bar a{color:#4c9aff}
.cc-bar button{font:inherit;font-weight:600;padding:9px 18px;border-radius:7px;cursor:pointer;
border:1px solid #5c6b80;background:#161d26;color:#dbe3ec}
.cc-bar button.yes{background:#4c9aff;border-color:#4c9aff;color:#06121f}
.cc-bar button:focus-visible{outline:2px solid #4c9aff;outline-offset:2px}
.cc-re{position:fixed;left:12px;bottom:10px;z-index:998;font:12px system-ui,sans-serif;
color:#9aa7b4;background:#12181f;border:1px solid #232c38;border-radius:6px;
padding:4px 9px;cursor:pointer}
</style>
<script>(function(){
var KEY='algostudio.consent';
function load(){var s=document.createElement('script');s.defer=true;s.src=${JSON.stringify(src)};${attrs}
document.head.appendChild(s);}
function get(){try{return localStorage.getItem(KEY);}catch(e){return null;}}
function set(v){try{localStorage.setItem(KEY,v);}catch(e){}}
function reopen(){
  var b=document.createElement('button');b.className='cc-re';b.type='button';
  b.textContent='Cookie settings';
  b.onclick=function(){b.remove();ask();};
  document.body.appendChild(b);
}
function ask(){
  var bar=document.createElement('div');
  bar.className='cc-bar';bar.setAttribute('role','dialog');
  bar.setAttribute('aria-label','Cookie consent');
  var p=document.createElement('p');
  p.innerHTML='We would like to set an analytics cookie to count visits. '+
    'It is not required for the site to work, and declining changes nothing. '+
    '<a href="/privacy">Privacy policy</a>.';
  var yes=document.createElement('button');yes.type='button';yes.className='yes';
  yes.textContent='Accept';
  var no=document.createElement('button');no.type='button';no.textContent='Decline';
  yes.onclick=function(){set('granted');bar.remove();load();reopen();};
  no.onclick=function(){set('denied');bar.remove();reopen();};
  bar.appendChild(p);bar.appendChild(no);bar.appendChild(yes);
  document.body.appendChild(bar);
  yes.focus();
}
function start(){var c=get();if(c==='granted'){load();reopen();}
else if(c==='denied'){reopen();}else{ask();}}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);
else start();
})();</script>`;
}

/**
 * Build-time SEO and performance pass.
 *
 * Does four things no amount of hand-editing keeps correct for long:
 * substitutes the real origin into canonical/OG tags, injects the analytics
 * snippet only when one is configured, inlines the CSS of pages that carry no
 * JavaScript, and emits robots.txt and sitemap.xml from PAGES.
 */
function sitePlugin(): Plugin {
  const analyticsSrc = process.env.VITE_ANALYTICS_SRC ?? "";
  const analyticsDomain = process.env.VITE_ANALYTICS_DOMAIN ?? "";

  // Set this only for a provider that stores something on the visitor's
  // device -- Google Analytics, say. It changes the law that applies: a
  // cookieless aggregate counter needs no opt-in, a cookie does.
  const needsConsent = process.env.VITE_ANALYTICS_CONSENT === "1";

  const scriptTag = analyticsSrc
    ? `<script defer src="${analyticsSrc}"${
        analyticsDomain ? ` data-domain="${analyticsDomain}"` : ""
      }></script>`
    : "";

  // Plausible- and Umami-compatible: one deferred script, no cookies, no
  // personal data, therefore nothing to ask consent for. If this is empty --
  // the default -- the page ships with no third-party request at all.
  //
  // Where consent IS required the script is not emitted at all; the snippet
  // below loads it only after an explicit yes. Nothing is injected in the
  // default configuration, so the content pages keep their zero-JavaScript
  // property rather than carrying a banner they will never show.
  const analyticsTag = !analyticsSrc
    ? "<!-- analytics: none configured (VITE_ANALYTICS_SRC unset) -->"
    : needsConsent
      ? consentSnippet(analyticsSrc, analyticsDomain)
      : scriptTag;

  let outDir = "dist";

  return {
    name: "algostudio-site",

    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },

    transformIndexHtml: {
      order: "pre",
      handler(html) {
        return html
          .replaceAll("%SITE_URL%", SITE_URL)
          .replaceAll("%YEAR%", String(new Date().getFullYear()))
          .replace("<!--ANALYTICS-->", analyticsTag);
      },
    },

    generateBundle() {
      // ---- robots.txt --------------------------------------------------
      this.emitFile({
        type: "asset",
        fileName: "robots.txt",
        source: [
          "# AlgoStudio",
          "User-agent: *",
          "Allow: /",
          "",
          "# The API returns JSON and the recordings behind it are ephemeral;",
          "# there is nothing here for an index, and crawling it costs the",
          "# free tier real CPU.",
          "Disallow: /api/",
          "Disallow: /ws/",
          "",
          `Sitemap: ${SITE_URL}/sitemap.xml`,
          "",
        ].join("\n"),
      });

      // ---- sitemap.xml -------------------------------------------------
      const today = new Date().toISOString().slice(0, 10);
      const urls = PAGES.filter((p) => p.url !== null)
        .map((p) =>
          [
            "  <url>",
            `    <loc>${SITE_URL}${p.url === "/" ? "/" : p.url}</loc>`,
            `    <lastmod>${today}</lastmod>`,
            `    <changefreq>${p.changefreq ?? "monthly"}</changefreq>`,
            `    <priority>${p.priority ?? "0.5"}</priority>`,
            "  </url>",
          ].join("\n"),
        )
        .join("\n");
      this.emitFile({
        type: "asset",
        fileName: "sitemap.xml",
        source:
          '<?xml version="1.0" encoding="UTF-8"?>\n' +
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          `${urls}\n</urlset>\n`,
      });
    },

    /**
     * Inline the CSS of the JavaScript-free pages.
     *
     * This runs on the written files rather than in `generateBundle`, because
     * Vite's own HTML plugin injects the <link> tags in its generateBundle and
     * there is no ordering that reliably puts us after it. By closeBundle the
     * files exist, the links are final, and a string replace cannot race.
     */
    closeBundle() {
      const inlined = new Set<string>();

      for (const page of PAGES.filter((p) => p.inlineCss)) {
        const htmlPath = join(outDir, page.file);
        let html: string;
        try {
          html = readFileSync(htmlPath, "utf-8");
        } catch {
          continue;
        }
        const next = html.replace(
          /<link[^>]*rel="stylesheet"[^>]*href="\/?([^"]+\.css)"[^>]*>/g,
          (match, href: string) => {
            const relative = href.replace(/^\//, "");
            try {
              const css = readFileSync(join(outDir, relative), "utf-8");
              inlined.add(relative);
              return `<style>${css}</style>`;
            } catch {
              return match;
            }
          },
        );
        if (next !== html) writeFileSync(htmlPath, next);
      }

      // Delete a stylesheet only once no page still links to it.
      const htmlFiles = readdirSync(outDir).filter((f) => f.endsWith(".html"));
      for (const name of inlined) {
        const stillLinked = htmlFiles.some((file) =>
          readFileSync(join(outDir, file), "utf-8").includes(name),
        );
        if (!stillLinked) rmSync(join(outDir, name), { force: true });
      }

      if (inlined.size) {
        console.log(`  inlined ${inlined.size} stylesheet(s) into JS-free pages`);
      }
    },
  };
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), sitePlugin()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target, changeOrigin: true },
      "/ws": { target: target.replace(/^http/, "ws"), ws: true },
    },
  },
  build: {
    outDir: "dist",
    // Source maps are 3x the size of the bundle they describe. Useful while
    // developing, pure transfer cost on a free tier.
    sourcemap: mode !== "production",
    rollupOptions: {
      input: Object.fromEntries(
        PAGES.map((p) => [p.file.replace(/\.html$/, ""), resolve(__dirname, p.file)]),
      ),
      output: {
        // React barely changes between deploys; the app changes every time.
        // Splitting them means a redeploy re-downloads ~70 KB, not ~215 KB.
        manualChunks: (id) =>
          id.includes("node_modules/react") || id.includes("node_modules/scheduler")
            ? "react"
            : undefined,
      },
    },
  },
}));
