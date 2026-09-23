import type { StepMode } from "../store/useExecution";
import { Icon } from "./Icon";

/**
 * The playback bar.
 *
 * Laid out in the order someone reaches for things: the big controls that move
 * through time, then where you are, then how playback behaves, then the
 * debugger's function-level stepping -- which a first-time visitor rarely
 * needs, so it comes last and is labelled rather than symbolised.
 *
 * It used to be eight unlabelled glyphs. Their meaning lived only in hover
 * tooltips, which do not exist on a touch screen, so on a phone the controls
 * were a row of arrows with no way to learn what they did.
 */
export function Transport({
  step, lastStep, playing, speed, stepMode, enabled,
  onSeek, onStepBack, onStepForward, onTogglePlay, onReplay, onJumpEnd,
  onStepOver, onStepInto, onStepOut, onSpeed, onStepMode,
}: {
  step: number;
  lastStep: number;
  playing: boolean;
  speed: number;
  stepMode: StepMode;
  enabled: boolean;
  onSeek: (step: number) => void;
  onStepBack: () => void;
  onStepForward: () => void;
  onTogglePlay: () => void;
  onReplay: () => void;
  onJumpEnd: () => void;
  onStepOver: () => void;
  onStepInto: () => void;
  onStepOut: () => void;
  onSpeed: (speed: number) => void;
  onStepMode: (mode: StepMode) => void;
}) {
  const position = Math.max(0, step);
  const percent = lastStep > 0 ? (position / lastStep) * 100 : 0;

  return (
    <div className="transport-bar" role="toolbar" aria-label="Playback">
      <div className="t-group t-main">
        <button
          className="t-btn icon-only"
          onClick={onReplay}
          disabled={!enabled}
          aria-label="Restart from the beginning"
          title="Restart  (Home)"
        >
          <Icon name="restart" />
        </button>
        <button
          className="t-btn"
          onClick={onStepBack}
          disabled={!enabled}
          aria-label="Step back"
          title="Step back  (←)"
        >
          <Icon name="back" />
          <span className="t-label">Back</span>
        </button>
        <button
          className="t-btn t-play"
          onClick={onTogglePlay}
          disabled={!enabled}
          aria-label={playing ? "Pause" : "Play"}
          aria-pressed={playing}
          title={playing ? "Pause  (space)" : "Play  (space)"}
        >
          <Icon name={playing ? "pause" : "play"} size={18} />
          <span className="t-label">{playing ? "Pause" : "Play"}</span>
        </button>
        <button
          className="t-btn"
          onClick={onStepForward}
          disabled={!enabled}
          aria-label="Step forward"
          title="Step forward  (→)"
        >
          <span className="t-label">Forward</span>
          <Icon name="forward" />
        </button>
        <button
          className="t-btn icon-only"
          onClick={onJumpEnd}
          disabled={!enabled}
          aria-label="Jump to the end"
          title="Jump to the end  (End)"
        >
          <Icon name="end" />
        </button>
      </div>

      <div className="t-group t-position">
        <span className="step-counter" aria-live="off">
          <span className="sc-now">{enabled ? position : "–"}</span>
          <span className="sc-sep">/</span>
          <span className="sc-total">{enabled ? lastStep : "–"}</span>
        </span>
        <div className="scrub">
          <input
            type="range"
            min={0}
            max={Math.max(0, lastStep)}
            value={position}
            onChange={(e) => onSeek(+e.target.value)}
            disabled={!enabled}
            aria-label="Position in the recording"
            aria-valuetext={enabled ? `step ${position} of ${lastStep}` : "nothing recorded"}
            style={{ ["--played" as string]: `${percent}%` }}
          />
        </div>
      </div>

      <div className="t-group t-options">
        <label className="ctl">
          <span>Step by</span>
          <select
            value={stepMode}
            onChange={(e) => onStepMode(e.target.value as StepMode)}
            disabled={!enabled}
          >
            <option value="line">Line</option>
            <option value="operation">Operation</option>
            <option value="event">Event</option>
          </select>
        </label>
        <label className="ctl speed">
          <span>Speed</span>
          <input
            type="range"
            min={1}
            max={60}
            value={speed}
            onChange={(e) => onSpeed(+e.target.value)}
            aria-valuetext={`${speed} steps per second`}
          />
          <span className="speed-value">{speed}/s</span>
        </label>
      </div>

      <div className="t-group t-debug" role="group" aria-label="Step through functions">
        <button
          className="t-btn t-small"
          onClick={onStepInto}
          disabled={!enabled}
          title="Step into the next function call"
        >
          <Icon name="into" size={14} />
          <span className="t-label">Into</span>
        </button>
        <button
          className="t-btn t-small"
          onClick={onStepOver}
          disabled={!enabled}
          title="Step over calls, staying in this function"
        >
          <Icon name="over" size={14} />
          <span className="t-label">Over</span>
        </button>
        <button
          className="t-btn t-small"
          onClick={onStepOut}
          disabled={!enabled}
          title="Run until this function returns"
        >
          <Icon name="out" size={14} />
          <span className="t-label">Out</span>
        </button>
      </div>
    </div>
  );
}
