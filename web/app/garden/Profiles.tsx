"use client";

/** One line of a twin's persona and what it's about (garden/speed_dating.py `about`). */
export type ProfileLine = { text: string; about: string };
export type Profiles = Record<string, ProfileLine[]>;

const ICON: Record<string, string> = {
  age: "🎂",
  studies: "📚",
  career: "💼",
  home: "📍",
  "why I'm here": "🎯",
  dating: "💌",
  "going out": "🌃",
  loves: "❤️",
  "not for me": "🙅",
  "wants in a partner": "💞",
  "sees self as": "🪞",
  "must share": "🤝",
  personality: "🧠",
  "about me": "•",
};

// The same palette as the map's people (GardenMap SHIRTS), so a card matches its sprite.
const COLORS = ["#d1495b", "#2e86ab", "#f18f01", "#6a4c93", "#3d8361", "#8d6346", "#247ba0", "#b5838d"];

const find = (lines: ProfileLine[], about: string) => lines.find((l) => l.about === about)?.text ?? "";
const strip = (text: string, prefix: RegExp) => text.replace(prefix, "").replace(/\.$/, "");

/** The short line under a twin's name: "21 · Law · Chicago". */
function summary(lines: ProfileLine[]): string {
  const age = find(lines, "age").match(/\d+/)?.[0];
  const studies = strip(find(lines, "studies"), /^I study /);
  const home = strip(find(lines, "home"), /^Before university, I lived in /);
  return [age, studies, home].filter(Boolean).join(" · ");
}

/** Everything the twin knows about themselves, one line each, with what it's about. */
export function ProfileList({ lines }: { lines: ProfileLine[] }) {
  return (
    <ul className="profile-list">
      {lines.map((l) => (
        <li key={l.text}>
          <span className="profile-icon" title={l.about} aria-label={l.about}>
            {ICON[l.about] ?? "•"}
          </span>
          {l.text}
        </li>
      ))}
    </ul>
  );
}

/** Who's in the Garden: one card per twin, built from what each twin was told about themselves. */
export default function TwinRoster({
  twins,
  profiles,
  her,
  matched,
  selected,
  onSelect,
}: {
  twins: string[];
  profiles: Profiles;
  her: string | null;
  matched: string[] | null;
  selected: string | null;
  onSelect: (twin: string) => void;
}) {
  if (!twins.some((t) => profiles[t]?.length)) return null;
  return (
    <section className="result roster" aria-label="The twins">
      <h2>The twins</h2>
      <p className="meta">What each twin knows about themselves: everything it was given to be that person.</p>
      <ul className="roster-grid">
        {twins.map((name, i) => {
          const lines = profiles[name] ?? [];
          const loves = strip(find(lines, "loves"), /^I love /);
          const wants = strip(find(lines, "wants in a partner"), /^In a partner, what matters most to me is that they are /);
          return (
            <li key={name}>
              <button
                className={`twin-card${name === selected ? " on" : ""}${name === her ? " her" : ""}`}
                onClick={() => onSelect(name)}
                aria-pressed={name === selected}
              >
                <span className="twin-avatar" style={{ background: COLORS[i % COLORS.length] }} aria-hidden>
                  {name.slice(0, 1)}
                </span>
                <span className="twin-card-body">
                  <span className="twin-card-name">
                    {name}
                    {name === her && <span className="badge her">her twin</span>}
                    {matched?.includes(name) && (
                      <span className="badge match" title={`${her} and ${name} matched at the real speed-dating event`}>
                        💞 real match
                      </span>
                    )}
                  </span>
                  {summary(lines) && <span className="twin-card-line">{summary(lines)}</span>}
                  {loves && <span className="twin-card-line">❤️ {loves}</span>}
                  {wants && <span className="twin-card-line">💞 wants {wants}</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
