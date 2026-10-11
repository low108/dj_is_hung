"use client";

export const isWallCrossing = (e: { rung: string | null }) => e.rung === "go_beyond_wall";

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

type Marker = { id: string; emoji: string; label: string; matches: (e: TimelineEvent) => boolean };

// The moments worth jumping to (E5): separations, gatherings, seek-outs, proposals and wall crossings.
const MARKERS: Marker[] = [
  { id: "separation", emoji: "💔", label: "Separation", matches: (e) => e.announcement_kind === "ended" },
  { id: "gathering", emoji: "🎉", label: "Gathering", matches: (e) => e.announcement_kind === "gathering" },
  { id: "seek_out", emoji: "👀", label: "Seek-out", matches: (e) => e.rung === "seek_out" },
  { id: "proposal", emoji: "💌", label: "Proposal", matches: (e) => e.rung === "propose_leaving" },
  { id: "wall", emoji: "🧱", label: "Wall crossing", matches: (e) => isWallCrossing(e) },
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
  atDay,
  onJump,
}: {
  events: TimelineEvent[];
  days: number;
  atSeq: number; // the last event the map has played
  atDay: number; // the day the map is on
  onJump: (seq: number) => void;
}) {
  const span = Math.max(days, 1);
  const dayLeft = (day: number) => `${((day - 0.5) / span) * 100}%`;
  return (
    <div className="timeline" data-testid="timeline">
      <div className="timeline-days">
        {Array.from({ length: span }, (_, i) => (
          <span key={i} style={{ left: dayLeft(i + 1) }} className={i + 1 === atDay ? "now" : ""}>
            {i + 1}
          </span>
        ))}
      </div>
      {MARKERS.map((m) => {
        const hits = events.filter(m.matches);
        return (
          <div key={m.id} className="timeline-row" data-kind={m.id}>
            <span className="timeline-label">
              {m.emoji} {m.label}
            </span>
            <div className="timeline-track">
              {hits.map((e, i) => {
                // Several on one day sit side by side rather than on top of each other.
                const nth = hits.slice(0, i).filter((h) => h.day === e.day).length;
                const text = describe(e, m.label);
                return (
                  <button
                    key={e.seq}
                    className={`marker${e.seq <= atSeq ? " past" : ""}`}
                    style={{ left: `calc(${dayLeft(e.day)} + ${nth * 6}px)` }}
                    title={text}
                    aria-label={text}
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
