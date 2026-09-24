import type { AIAnswer, AsEvent, ViewDescriptor } from "../api/types";

/**
 * The execution engine, running in this tab instead of on the server.
 *
 * The public deployment refuses to execute source a visitor typed
 * (`ALGOSTUDIO_ALLOW_ARBITRARY_CODE=0`) because a free instance has no
 * per-execution container sandbox, and the in-process restrictions are defense
 * in depth rather than a boundary. This is the way round that without
 * weakening the claim: the code never reaches the server at all. It runs here,
 * on the machine of the person who wrote it, inside the browser's own sandbox.
 *
 * The Python is the *same* Python — `algostudio.browser.engine` composes the
 * identical instrument → execute → lift → reduce → resolve pipeline the server
 * runs, on top of the same `runtime/child_main.py`. docs/21-pyodide-spike.md
 * establishes that this produces a byte-identical event stream for 49 of 51
 * fixtures, the two exceptions being set-iteration order, which Python does not
 * define and which differs between any two CPython builds of different word
 * size.
 */

export type EngineStage =
  | "idle" | "downloading" | "starting" | "unpacking" | "ready" | "unavailable";

export interface EngineStatus {
  stage: EngineStage;
  message: string;
}

export interface BrowserRunResult {
  status: string;
  error: { type?: string; message?: string; line?: number } | null;
  capability_report: any;
  event_count: number;
  wall_ms: number;
  last_step: number;
  events: AsEvent[];
  analytics: any;
  meta: any;
}

export interface BrowserEngine {
  run(source: string, granularity: string): BrowserRunResult;
  views(step: number): ViewDescriptor[];
  /** The tutor, answered from the run held in this tab. */
  ask(step: number, mode: string, question: string, variable: string): AIAnswer;
}

/**
 * The engine instance, if it has already been loaded -- without starting a
 * load. The tutor uses this: asking about a browser run only makes sense once
 * that run exists, and by then the engine is necessarily loaded.
 */
export function loadedBrowserEngine(): Promise<BrowserEngine> | null {
  return enginePromise;
}

type StatusFn = (status: EngineStatus) => void;

let enginePromise: Promise<BrowserEngine> | null = null;

/**
 * Is the in-browser engine even shipped with this build?
 *
 * A backend-only checkout, or a build made without `fetch-pyodide`, has
 * neither the runtime nor the engine bundle. The app must then behave exactly
 * as it did before rather than offering an editor that cannot work — so this
 * is checked before anything is offered, not after it fails.
 */
export async function browserEngineAvailable(): Promise<boolean> {
  try {
    const [runtime, bundle] = await Promise.all([
      fetch("/pyodide/version.json", { method: "GET", cache: "no-cache" }),
      fetch("/engine/algostudio.zip", { method: "HEAD", cache: "no-cache" }),
    ]);
    return runtime.ok && bundle.ok;
  } catch {
    return false;
  }
}

export function getBrowserEngine(onStatus: StatusFn = () => {}): Promise<BrowserEngine> {
  // One load per tab. The runtime is ~5 MB over the wire and several hundred
  // milliseconds to start, so a second `Run` must not pay for it again.
  if (!enginePromise) {
    enginePromise = load(onStatus).catch((err) => {
      enginePromise = null;               // let a later attempt retry
      throw err;
    });
  }
  return enginePromise;
}

async function load(onStatus: StatusFn): Promise<BrowserEngine> {
  onStatus({ stage: "downloading", message: "Downloading the Python runtime (~5 MB)…" });

  // Both are revalidated rather than trusted from cache: they change with a
  // deploy while keeping their names (see _RevalidatedStatic in api/app.py).
  const version = await fetch("/pyodide/version.json", { cache: "no-cache" }).then((r) => r.json());
  const indexURL: string = version.indexURL;

  // Imported at runtime from our own origin — deliberately not from a CDN,
  // because the privacy policy states there are no third-party requests and
  // that has to stay true.
  const { loadPyodide } = await import(/* @vite-ignore */ `${indexURL}pyodide.mjs`);

  onStatus({ stage: "starting", message: "Starting Python…" });
  const pyodide = await loadPyodide({
    indexURL,
    // Set iteration order is part of the event stream, so the browser runs
    // under the same fixed hash seed the server's sandbox pins in clean_env().
    env: { PYTHONHASHSEED: "0" },
  });

  onStatus({ stage: "unpacking", message: "Loading the AlgoStudio engine…" });
  const bundle = await fetch("/engine/algostudio.zip", { cache: "no-cache" }).then((r) => r.arrayBuffer());
  pyodide.unpackArchive(bundle, "zip");

  const engine = pyodide.pyimport("algostudio.browser.engine");

  onStatus({ stage: "ready", message: "Ready — your code runs in this tab." });

  return {
    run(source: string, granularity: string): BrowserRunResult {
      return JSON.parse(engine.run(source, granularity));
    },
    views(step: number): ViewDescriptor[] {
      return JSON.parse(engine.views(step));
    },
    ask(step: number, mode: string, question: string, variable: string): AIAnswer {
      return JSON.parse(engine.ask(step, mode, question, variable));
    },
  };
}
