"use client";

import { useEffect, useRef } from "react";
import { ZONES, isArea } from "./world";

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
  venue?: string | null;
};

type Marker = { id: string; emoji: string; label: string; matches: (e: TimelineEvent) => boolean };

// The moments worth jumping to (E5): the day the wall opens (#63), separations, gatherings, seek-outs,
// proposals and wall crossings.
const MARKERS: Marker[] = [
  { id: "wall_open", emoji: "🚪", label: "Everyone has met", matches: (e) => e.announcement_kind === "wall_open" },
  { id: "pairing_day", emoji: "💍", label: "Pairing Day", matches: (e) => e.announcement_kind === "pairing_day" },
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

type DayCard = {
  day: number;
  first: number; // the day's first seq: where clicking the card jumps
  with: string | null; // who she's paired with that day
  gathering: boolean;
  venue: string | null; // "🏀 Sports court" (scene pass)
  moments: { marker: Marker; events: TimelineEvent[] }[];
};

function dayCards(events: TimelineEvent[], days: number, her: string | null): DayCard[] {
  const cards: DayCard[] = [];
  let partner: string | null = null;
  for (let day = 1; day <= Math.max(days, 1); day++) {
    const today = events.filter((e) => e.day === day);
    for (const e of today) {
      if (!her || !e.announcement?.includes(her)) continue;
      if (e.announcement_kind === "paired") partner = e.announcement.split(":")[0].split(" and ").find((n) => n !== her) ?? null;
      if (e.announcement_kind === "ended") partner = null;
    }
    const gathering = today.some((e) => e.announcement_kind === "gathering");
    const venue = today.find((e) => isArea(e.venue) && (e.twin === her || e.target === her))?.venue;
    cards.push({
      day,
      first: today[0]?.seq ?? 0,
      with: gathering ? null : partner,
      gathering,
      venue: isArea(venue) ? `${ZONES[venue].icon} ${ZONES[venue].label}` : null,
      moments: MARKERS.map((marker) => ({ marker, events: today.filter(marker.matches) })).filter((m) => m.events.length),
    });
  }
  return cards;
}

/** The run's days as a row of cards you scroll sideways: who she's with and where, and the day's
 * moments as chips. Click a card (or a chip) to jump the map there; the row follows the day playing. */
export default function Timeline({
  events,
  days,
  atSeq,
  atDay,
  her = null,
  onJump,
}: {
  events: TimelineEvent[];
  days: number;
  atSeq: number; // the last event the map has played
  atDay: number; // the day the map is on
  her?: string | null;
  onJump: (seq: number) => void;
}) {
  const strip = useRef<HTMLOListElement>(null);
  useEffect(() => {
    const row = strip.current;
    const card = row?.querySelector<HTMLElement>(`[data-day="${atDay}"]`);
    if (card && row) row.scrollTo({ left: card.offsetLeft - row.clientWidth / 2 + card.clientWidth / 2, behavior: "smooth" });
  }, [atDay]);

  const cards = dayCards(events, days, her);
  return (
    <div className="timeline" data-testid="timeline">
      <ol className="day-strip" ref={strip} aria-label="Days">
        {cards.map((c) => {
          const state = c.day === atDay ? " now" : c.day < atDay ? " past" : "";
          return (
            <li key={c.day} data-day={c.day} className={`day-card${c.gathering ? " gathering" : ""}${state}`}>
              <button className="day-card-main" onClick={() => c.first && onJump(c.first)} disabled={!c.first}>
                <span className="day-card-day">Day {c.day}</span>
                <span className="day-card-who">{c.gathering ? "🎉 Gathering" : c.with ? `with ${c.with}` : "—"}</span>
                {c.venue && <span className="day-card-where">{c.venue}</span>}
              </button>
              {c.moments.length > 0 && (
                <span className="day-card-moments">
                  {c.moments.map(({ marker, events: hits }) => (
                    <button
                      key={marker.id}
                      className={`moment${hits[0].seq <= atSeq ? " seen" : ""}`}
                      title={hits.map((e) => describe(e, marker.label)).join("\n")}
                      aria-label={`${marker.label} on day ${c.day}`}
                      onClick={() => onJump(hits[0].seq)}
                    >
                      {marker.emoji}
                      {hits.length > 1 && <sub>{hits.length}</sub>}
                    </button>
                  ))}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
