// Download the Pyodide runtime into public/pyodide so it is served from our
// own origin.
//
// Loading it from a CDN would cost nothing and require no build step. It would
// also make the privacy policy false: that page states there are no
// third-party requests, and a CDN sees every visitor's IP and user agent. We
// spent the effort to make that claim literally true, and 6 MB of image is a
// cheaper price than an asterisk on it.
//
//   node scripts/fetch-pyodide.mjs
//
// Idempotent: files already present with the right size are left alone.

import { mkdir, writeFile, stat } from "node:fs/promises";
import { gzipSync } from "node:zlib";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const VERSION = "0.28.3";
const BASE = `https://cdn.jsdelivr.net/pyodide/v${VERSION}/full`;
// Versioned directory, so the files can be cached forever: a Pyodide upgrade
// changes the path rather than the contents behind a stale URL.
const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "public",
                 "pyodide", VERSION);

// The minimum for running pure Python with no third-party packages. Anything
// else Pyodide wants, it derives from these.
const FILES = [
  "pyodide.js",
  "pyodide.mjs",
  "pyodide.asm.js",
  "pyodide.asm.wasm",
  "python_stdlib.zip",
  "pyodide-lock.json",
];

async function exists(path) {
  try {
    const info = await stat(path);
    return info.size > 0;
  } catch {
    return false;
  }
}

async function main() {
  await mkdir(OUT, { recursive: true });
  let fetched = 0;
  let total = 0;

  for (const name of FILES) {
    const target = join(OUT, name);
    if (await exists(target)) {
      const info = await stat(target);
      total += info.size;
      console.log(`  cached   ${name.padEnd(20)} ${(info.size / 1024).toFixed(0)} KB`);
      continue;
    }
    const response = await fetch(`${BASE}/${name}`);
    if (!response.ok) {
      throw new Error(`${name}: ${response.status} ${response.statusText}`);
    }
    const bytes = Buffer.from(await response.arrayBuffer());
    await writeFile(target, bytes);
    fetched++;
    total += bytes.length;

    // Pre-compress the large ones. The alternative is gzipping 8 MB of wasm on
    // every cold visit, on an instance with a tenth of a CPU -- which is both
    // slow and CPU the server does not have to spare.
    let note = "";
    if (bytes.length > 256 * 1024) {
      const gz = gzipSync(bytes, { level: 9 });
      await writeFile(`${target}.gz`, gz);
      note = ` -> ${(gz.length / 1024).toFixed(0)} KB gzipped`;
    }
    console.log(`  fetched  ${name.padEnd(20)} ${(bytes.length / 1024).toFixed(0)} KB${note}`);
  }

  // The app reads this to build its indexURL, so the version lives in exactly
  // one place: the constant at the top of this script.
  await writeFile(
    join(OUT, "..", "version.json"),
    JSON.stringify({ version: VERSION, indexURL: `/pyodide/${VERSION}/` }),
    "utf-8",
  );
  console.log(
    `  pyodide ${VERSION}: ${FILES.length} files, ` +
    `${(total / 1024 / 1024).toFixed(1)} MB total (${fetched} newly fetched)`,
  );
}

main().catch((err) => {
  console.error(`\nfailed to fetch pyodide: ${err.message}`);
  console.error("the site still builds; the in-browser engine will be unavailable");
  process.exit(1);
});
