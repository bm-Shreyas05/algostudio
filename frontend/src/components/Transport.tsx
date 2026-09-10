import type { StepMode } from "../store/useExecution";

/**
 * The playback bar.
 *
 * Everything that moves the cursor lives here, on its own full-width row. It
 * used to be crammed into the right-hand end of the toolbar, where the speed
 * control was simply pushed off-screen on any window narrower than ~1050px.
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
  const percent = lastStep > 0 ? (Math.max(0, step) / lastStep) * 100 : 0;

  return (
    <div className="transport-bar">
      <div className="transport-buttons">
        <button onClick={onReplay} disabled={!enabled} title="Replay from the start">
          ⟲
        </button>
        <button onClick={onStepOut} disabled={!enabled} title="Step out of this function">
          ⤴
        </button>
        <button onClick={onStepBack} disabled={!enabled} title="Step back  (←)">
          ◀
        </button>
        <button
          className="play"
          onClick={onTogglePlay}
          disabled={!enabled}
          title={playing ? "Pause  (space)" : "Play  (space)"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <button onClick={onStepForward} disabled={!enabled} title="Step forward  (→)">
          ▶
        </button>
        <button onClick={onStepOver} disabled={!enabled} title="Step over">
          ⤵
        </button>
        <button onClick={onStepInto} disabled={!enabled} title="Step into a call">
          ↘
        </button>
        <button onClick={onJumpEnd} disabled={!enabled} title="Jump to the end">
          ⇥
        </button>
      </div>

      <span className="step-counter" title="position in the recording">
        {enabled ? `${Math.max(0, step)} / ${lastStep}` : "— / —"}
      </span>

      <div className="scrub">
        <input
          type="range"
          min={0}
          max={Math.max(0, lastStep)}
          value={Math.max(0, step)}
          onChange={(e) => onSeek(+e.target.value)}
          disabled={!enabled}
          style={{ ["--played" as string]: `${percent}%` }}
          title="drag to scrub through the recording"
        />
      </div>

      <label className="ctl" title="How far one step moves">
        step by
        <select
          value={stepMode}
          onChange={(e) => onStepMode(e.target.value as StepMode)}
          disabled={!enabled}
        >
          <option value="line">line</option>
          <option value="operation">operation</option>
          <option value="event">event</option>
        </select>
      </label>

      <label className="ctl speed" title="Playback speed, steps per second">
        speed
        <input
          type="range"
          min={1}
          max={60}
          value={speed}
          onChange={(e) => onSpeed(+e.target.value)}
        />
        <span className="speed-value">{speed}/s</span>
      </label>
    </div>
  );
}
