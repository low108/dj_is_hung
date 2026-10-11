"use client";

import { useState } from "react";
import type { TwinState } from "./TwinPanel";

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

function Line({ e, her }: { e: LogEvent; her: string }) {
  const who = e.twin === her ? her : e.twin;
  const toward = e.target && e.target !== her ? ` → ${e.target}` : e.target === her && e.twin !== her ? ` → ${her}` : "";
  const what = CHOSE[e.rung ?? ""] ?? e.rung;
  const special = e.rung && !["talk", "reflect", "go_to"].includes(e.rung);
  return (
    <li className={`her-line ${e.twin === her ? "hers" : "his"}${special ? " special" : ""}`}>
      <span className="who">
        {e.emoji} {who}
        {toward}
      </span>
      {what && <span className="what"> chose “{what}”</span>}
      {e.say && <q> {e.say}</q>}
    </li>
  );
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
            <li key={d.day} className={`her-day ${d.kind}`}>
              <button className="her-day-head" onClick={() => toggle(d.day)} aria-expanded={shown}>
                <b>Day {d.day}</b> · {title(d)}
                <span className="meta">
                  {" "}
                  · {turns} turn{turns === 1 ? "" : "s"}
                  {d.lines.some((l) => l.rung === "propose_leaving" || l.rung === "go_beyond_wall") && " · 💌🧱"}
                </span>
              </button>
              {shown && (
                <>
                  {d.news.map((n) => (
                    <p key={n} className="meta news">
                      📣 {n}
                    </p>
                  ))}
                  <ul className="her-lines">
                    {d.lines.map((e) => (
                      <Line key={e.seq} e={e} her={her} />
                    ))}
                    {!d.lines.length && <li className="meta">Nothing yet.</li>}
                  </ul>
                  {reflection(d.day) && (
                    <blockquote className="her-reflection">
                      <span className="meta">🌙 That evening, {her} wrote privately:</span> {reflection(d.day)}
                    </blockquote>
                  )}
                </>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
