"use client";

/** What the viewer knows about a twin at its latest evening (GET /simulations/{id}/twins). */
export type TwinState = {
  day: number;
  twin: string;
  partner: string | null;
  days_left: number | null;
  standing: string;
  longing_hearts: Record<string, number>;
  reflection: string;
};

export default function TwinPanel({ state, onClose }: { state: TwinState | undefined; onClose: () => void }) {
  if (!state) return null;
  const hearts = Object.entries(state.longing_hearts).sort((a, b) => b[1] - a[1]);
  return (
    <aside className="twin-panel" data-testid="twin-panel">
      <header>
        <h3>{state.twin}</h3>
        <button className="link" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </header>
      <p className="meta">As of the evening of day {state.day}</p>
      <dl>
        <dt>Partner</dt>
        <dd>
          {state.partner
            ? `${state.partner}, ${state.days_left === 1 ? "one more day" : `${state.days_left} more days`}`
            : "Between assignments"}
        </dd>
        {state.standing && (
          <>
            <dt>Standing</dt>
            <dd>{state.standing}</dd>
          </>
        )}
        <dt>Longing</dt>
        <dd>
          {hearts.length
            ? hearts.map(([who, n]) => (
                <span key={who} className="hearts">
                  {who} {"♥".repeat(n)}
                  {"♡".repeat(3 - n)}
                </span>
              ))
            : "No one yet"}
        </dd>
        {state.reflection && (
          <>
            <dt>Tonight&apos;s reflection</dt>
            <dd className="reflection">“{state.reflection}”</dd>
          </>
        )}
      </dl>
      <p className="meta">Viewer only: twins never see hearts or numbers.</p>
    </aside>
  );
}
