"use client";

/** The fields of a feed event (docs/event-contract.md) the timeline uses. */
export type TimelineEvent = {
  seq: number;
  day: number;
  twin: string | null;
  rung: string | null;
  target: string | null;
  announcement: string | null;
  announcement_kind: string | null;
};

type Marker = { kind: string; emoji: string; label: string; matches: (e: TimelineEvent) => boolean };

// The moments worth jumping to (E5): separations, gatherings, seek-outs, proposals and wall crossings.
export const MARKERS: Marker[] = [
  { kind: "separation", emoji: "💔", label: "Separation", matches: (e) => e.announcement_kind === "ended" },
  { kind: "gathering", emoji: "🎉", label: "Gathering", matches: (e) => e.announcement_kind === "gathering" },
  { kind: "seek_out", emoji: "👀", label: "Seek-out", matches: (e) => e.rung === "seek_out" },
  { kind: "proposal", emoji: "💌", label: "Proposal", matches: (e) => e.rung === "propose_leaving" },
  { kind: "wall", emoji: "🧱", label: "Wall crossing", matches: (e) => e.rung === "go_beyond_wall" },
];

function describe(e: TimelineEvent, label: string): string {
  if (e.announcement) return `Day ${e.day}: ${e.announcement}`;
  return `Day ${e.day}: ${label}, ${e.twin}${e.target ? ` → ${e.target}` : ""}`;
}

/** Days across, one row of markers per kind; click a marker to jump the map there. */
export default function Timeline({
  events,
  days,
  atSeq,
  onJump,
}: {
  events: TimelineEvent[];
  days: number;
  atSeq: number; // the last event the map has played
  onJump: (seq: number) => void;
}) {
  const span = Math.max(days, 1);
  const x = (day: number) => `${((day - 0.5) / span) * 100}%`;
  const atDay = events.find((e) => e.seq === atSeq)?.day ?? 0;
  return (
    <div className="timeline" data-testid="timeline">
      <div className="timeline-days">
        {Array.from({ length: span }, (_, i) => (
          <span key={i} style={{ left: x(i + 1) }} className={i + 1 === atDay ? "now" : ""}>
            {i + 1}
          </span>
        ))}
      </div>
      {MARKERS.map((m) => {
        const hits = events.filter(m.matches);
        return (
          <div key={m.kind} className="timeline-row" data-kind={m.kind}>
            <span className="timeline-label">
              {m.emoji} {m.label}
            </span>
            <div className="timeline-track">
              {hits.map((e, i) => {
                // Several on one day sit side by side rather than on top of each other.
                const nth = hits.slice(0, i).filter((h) => h.day === e.day).length;
                return (
                  <button
                    key={e.seq}
                    className={`marker${e.seq <= atSeq ? " past" : ""}`}
                    style={{ left: `calc(${x(e.day)} + ${nth * 6}px)` }}
                    title={describe(e, m.label)}
                    aria-label={describe(e, m.label)}
                    onClick={() => onJump(e.seq)}
                  >
                    {m.emoji}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
