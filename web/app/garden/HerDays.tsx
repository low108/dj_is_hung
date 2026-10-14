"use client";

import { useState } from "react";
import type { TwinState } from "./TwinPanel";
import { ZONES, isArea } from "./world";

/** The fields of a feed event (docs/event-contract.md) her log uses. */
export type LogEvent = {
  seq: number;
  day: number;
  twin: string | null;
  rung: string | null;
  target: string | null;
  say: string;
  emoji: string;
  announcement: string | null;
  announcement_kind: string | null;
  venue?: string | null; // where the date was (scene pass, garden/scenes.py)
  gist?: string[];
};

type Day = {
  day: number;
  kind: "date" | "gathering" | "waiting";
  partner: string | null;
  lines: LogEvent[]; // her turns, what was done toward her, and her date's turns, in order
  news: string[]; // the Coordinator's word about her that day
};

// The option the twin chose, in the words it was offered (garden/world_text.py RUNG_OPTIONS).
const CHOSE: Record<string, string> = {
  talk: "",
  go_to: "Go somewhere else in the Garden",
  reflect: "Spend some time alone, reflecting",
  seek_out: "Look for someone who is not your current partner",
  check_device: "Check your Coordinator device early",
  propose_leaving: "Ask someone to leave the Garden with you",
  go_beyond_wall: "Go beyond the wall with someone",
};

/** Her days, built from the feed: who she was with, and every line between her and the men. */
function herDays(events: LogEvent[], her: string): Day[] {
  const days = new Map<number, Day>();
  let partner: string | null = null;
  for (const e of events) {
    const d = days.get(e.day) ?? { day: e.day, kind: "waiting", partner, lines: [], news: [] };
    days.set(e.day, d);
    if (e.announcement) {
      const about = e.announcement.includes(her);
      if (e.announcement_kind === "paired" && about) {
        partner = e.announcement.split(":")[0].split(" and ").find((n) => n !== her) ?? null;
        d.kind = "date";
        d.partner = partner;
      } else if (e.announcement_kind === "ended" && about) {
        partner = null;
        d.partner = null;
      } else if (e.announcement_kind === "gathering") {
        d.kind = "gathering";
      }
      if (about || e.announcement_kind === "gathering" || e.announcement_kind === "wall_open" || e.announcement_kind === "pairing_day")
        d.news.push(e.announcement);
      continue;
    }
    if (d.kind === "waiting" && partner) {
      d.kind = "date";
      d.partner = partner;
    }
    // Her turns, anything aimed at her, and on a date everything her partner did (even on his own).
    if (e.twin === her || e.target === her || (d.kind === "date" && e.twin === d.partner)) d.lines.push(e);
  }
  return [...days.values()].sort((a, b) => b.day - a.day); // newest first
}

function title(d: Day): string {
  if (d.kind === "gathering") return "Gathering at the hall";
  if (d.kind === "date" && d.partner) return `On a date with ${d.partner}`;
  return "Between dates";
}

/** One turn in the thread: a line of speech is a chat bubble (hers on the right, his on the left);
 * a turn without words is a small centred note of what was chosen. */
function Line({ e, her }: { e: LogEvent; her: string }) {
  const side = e.twin === her ? "hers" : "his";
  const toward = e.target && !(e.twin !== her && e.target === her) ? ` → ${e.target}` : "";
  const what = CHOSE[e.rung ?? ""] ?? e.rung;
  const big = e.rung === "propose_leaving" || e.rung === "go_beyond_wall";
  if (!e.say)
    return (
      <li className={`turn move${big ? " big" : ""}`}>
        <span>
          {e.emoji} {e.twin} chose “{what || e.rung}”{toward}
        </span>
      </li>
    );
  return (
    <li className={`turn ${side}${big ? " big" : ""}`}>
      <div className="turn-meta">
        <b>{e.twin}</b>
        {toward}
        {what && <span className="chose"> · {what}</span>}
        {e.gist?.length ? <span className="gist">{e.gist.join("")}</span> : null}
      </div>
      <div className="bubble">
        {e.emoji !== "💬" && <span className="bubble-emoji">{e.emoji} </span>}
        {e.say}
      </div>
    </li>
  );
}

/** Where a date day happened, from the scene pass (the first event that has a venue). */
function venueOf(d: Day): string | null {
  const v = d.lines.find((l) => isArea(l.venue))?.venue;
  return isArea(v) ? `${ZONES[v].icon} ${ZONES[v].label}` : null;
}

/** Her twin's days, newest first: the current day open, earlier days one click away. */
export default function HerDays({
  events,
  her,
  evenings,
}: {
  events: LogEvent[];
  her: string;
  evenings: TwinState[]; // every twin's evening snapshots: her reflection is what she wrote that night
}) {
  const days = herDays(events, her);
  const reflection = (day: number) => evenings.find((s) => s.twin === her && s.day === day)?.reflection;
  const [open, setOpen] = useState<Set<number>>(new Set());
  if (!days.length) return null;
  const current = days[0].day;
  const toggle = (day: number) =>
    setOpen((old) => {
      const next = new Set(old);
      if (next.has(day)) next.delete(day);
      else next.add(day);
      return next;
    });

  return (
    <section className="result her-days" data-testid="her-days">
      <h2>{her}&apos;s days</h2>
      <ol className="her-days-list">
        {days.map((d) => {
          const shown = d.day === current || open.has(d.day);
          const turns = d.lines.filter((l) => l.twin === her).length;
          return (
            <li key={d.day} className={`her-day card ${d.kind}${shown ? " open" : ""}`}>
              <button className="her-day-head" onClick={() => toggle(d.day)} aria-expanded={shown}>
                <span className="day-badge">Day {d.day}</span>
                <span className="day-title">
                  {title(d)}
                  {venueOf(d) && <span className="venue"> · {venueOf(d)}</span>}
                </span>
                <span className="chips">
                  <span className="chip">
                    {turns} turn{turns === 1 ? "" : "s"}
                  </span>
                  {d.lines.some((l) => l.rung === "propose_leaving" || l.rung === "go_beyond_wall") && (
                    <span className="chip hot">💌🧱</span>
                  )}
                  <span className="caret" aria-hidden>
                    {shown ? "▾" : "▸"}
                  </span>
                </span>
              </button>
              {shown && (
                <div className="her-day-body">
                  {d.news.map((n) => (
                    <p key={n} className="news">
                      📣 {n}
                    </p>
                  ))}
                  <ul className="thread" aria-label={`Day ${d.day} conversation`}>
                    {d.lines.map((e) => (
                      <Line key={e.seq} e={e} her={her} />
                    ))}
                    {!d.lines.length && <li className="turn move">Nothing yet.</li>}
                  </ul>
                  {reflection(d.day) && (
                    <blockquote className="her-reflection">
                      <span className="diary-head">🌙 That evening, {her} wrote privately</span>
                      {reflection(d.day)}
                    </blockquote>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
