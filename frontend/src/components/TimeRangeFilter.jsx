import { useState } from "react";

// No tenant selector here or anywhere in this app — tenant is never a
// client-supplied filter in this system (it comes from the caller's JWT
// claim, enforced server-side), so a dropdown for it would contradict the
// architecture the backend half of this project enforces. See
// docs/DECISIONS.md.
const PRESETS = [
  { label: "Last 15m", ms: 15 * 60 * 1000 },
  { label: "Last 1h", ms: 60 * 60 * 1000 },
  { label: "Last 24h", ms: 24 * 60 * 60 * 1000 },
  { label: "Last 7d", ms: 7 * 24 * 60 * 60 * 1000 },
];

export default function TimeRangeFilter({ onChange }) {
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");

  function applyPreset(ms) {
    const end = new Date();
    const start = new Date(end.getTime() - ms);
    onChange({ startTime: start.toISOString(), endTime: end.toISOString() });
  }

  function applyCustom(event) {
    event.preventDefault();
    onChange({
      startTime: customStart ? new Date(customStart).toISOString() : null,
      endTime: customEnd ? new Date(customEnd).toISOString() : null,
    });
  }

  return (
    <div className="time-range-filter">
      <div className="time-range-presets">
        {PRESETS.map((preset) => (
          <button key={preset.label} type="button" onClick={() => applyPreset(preset.ms)}>
            {preset.label}
          </button>
        ))}
      </div>
      <form className="time-range-custom" onSubmit={applyCustom}>
        <label>
          From
          <input type="datetime-local" value={customStart} onChange={(event) => setCustomStart(event.target.value)} />
        </label>
        <label>
          To
          <input type="datetime-local" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} />
        </label>
        <button type="submit">Apply</button>
      </form>
    </div>
  );
}
