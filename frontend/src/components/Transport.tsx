import type { StepMode } from "../store/useExecution";
import { Icon } from "./Icon";
import { Popover } from "./Popover";

/**
 * The playback bar.
 *
 * Only what everyone uses: move through time, see where you are, set the
 * speed. How far a step moves, and the debugger's step into / over / out, are
 * one labelled menu away -- they matter when tracing your own functions and
 * not at all to someone watching a sort.
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
        <label className="ctl speed">
          <span>Speed</span>
          <input
            type="range"
            min={1}
            max={60}
            value={speed}
            onChange={(e) => onSpeed(+e.target.value)}
            aria-label="Playback speed"
            aria-valuetext={`${speed} steps per second`}
          />
          <span className="speed-value">{speed}/s</span>
        </label>
      </div>

      {/* Debugger stepping is a real need when you are tracing your own
          functions, and no use at all to someone watching a sort. It used to
          take a third of this bar; now it is one labelled menu away. */}
      <Popover
        label="Stepping options"
        trigger={<span className="t-more"><Icon name="steps" size={15} /><span className="t-label-always">Stepping</span></span>}
        wide
      >
        <div className="pop-section">
          <div className="pop-title">Each step moves by</div>
          <div className="seg" role="radiogroup" aria-label="Each step moves by">
            {(["line", "operation", "event"] as StepMode[]).map((m) => (
              <label key={m} className={`seg-opt${stepMode === m ? " on" : ""}`}>
                <input
                  type="radio"
                  name="stepmode"
                  checked={stepMode === m}
                  onChange={() => onStepMode(m)}
                />
                {m === "line" ? "One line" : m === "operation" ? "One change" : "Every event"}
              </label>
            ))}
          </div>
          <p className="pop-note">
            {stepMode === "line" ? "Like a debugger: one line of code at a time."
              : stepMode === "operation" ? "Skips reads; stops only where something changes."
              : "Everything the engine recorded, including each read."}
          </p>
        </div>
        <div className="pop-section">
          <div className="pop-title">Move through function calls</div>
          <div className="t-debug-row">
            <button className="t-btn t-small" onClick={onStepInto} disabled={!enabled}>
              <Icon name="into" size={14} />Step into
            </button>
            <button className="t-btn t-small" onClick={onStepOver} disabled={!enabled}>
              <Icon name="over" size={14} />Step over
            </button>
            <button className="t-btn t-small" onClick={onStepOut} disabled={!enabled}>
              <Icon name="out" size={14} />Step out
            </button>
          </div>
          <p className="pop-note">
            Into enters the next call, over runs it without stopping inside, and
            out finishes the current function.
          </p>
        </div>
      </Popover>
    </div>
  );
}
