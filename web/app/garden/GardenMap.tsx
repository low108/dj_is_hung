"use client";

import type Phaser from "phaser";
import { useEffect, useRef } from "react";
import { COLS, GATE, ROWS, TILE, ZONES, isPlace, isWall, spotFor, walkableGrid, type Place, type Tile } from "./world";

/** The fields of a feed event (docs/event-contract.md) that the map uses. */
export type MapEvent = {
  seq: number;
  day: number;
  twin: string | null;
  place: string | null;
  emoji: string;
  say: string;
  announcement: string | null;
};

/** Where playback is: the day and seq of the last event played; caughtUp when the queue is empty. */
export type Progress = { day: number; seq: number; caughtUp: boolean };

const BUBBLE_MS = 2600; // how long a line of speech stays above a twin

type Sprite = {
  body: Phaser.GameObjects.Arc;
  label: Phaser.GameObjects.Text;
  emoji: Phaser.GameObjects.Text;
  bubble: Phaser.GameObjects.Text;
  at: Tile;
  slot: number;
};

const STEP_MS = 90; // per tile while walking, at 1×
const COLORS = [0xd1495b, 0x2e86ab, 0xf18f01, 0x6a4c93, 0x3d8361, 0x8d6346, 0x247ba0, 0xb5838d];

/** The Garden drawn with Phaser. Plays feed events in order through a queue, walking each twin to
 * the place of its action along an EasyStar path; with `catchUp` it hurries through a live backlog.
 * `speed` scales every walk and timer; `paused` freezes playback where it is.
 * `startAt` begins playback at that seq, with each twin already where the events before it left them.
 * `finale` (a breakout pair) climbs the gate together once the last event has played.
 * Give it a `key` per simulation, replay or jump: each starts with a fresh map, queue and cursor. */
export default function GardenMap({
  events,
  twins,
  onSelect,
  onAnnouncement,
  onProgress,
  speed = 1,
  paused = false,
  catchUp = true,
  startAt = 0,
  finale = null,
}: {
  events: MapEvent[];
  twins: string[];
  onSelect?: (twin: string) => void;
  onAnnouncement?: (event: MapEvent) => void; // called when playback reaches it, so toasts match the map
  onProgress?: (progress: Progress) => void;
  speed?: number;
  paused?: boolean;
  catchUp?: boolean; // live: hurry through a backlog; replay: everything is queued at once, so don't
  startAt?: number;
  finale?: [string, string] | null;
}) {
  const host = useRef<HTMLDivElement>(null);
  const queue = useRef<MapEvent[]>([]);
  const firstSeq = useRef(startAt); // fixed for this map's life (a jump remounts it via `key`)
  const seen = useRef(firstSeq.current - 1); // events before it only decide where twins begin
  const resumePlayback = useRef<(() => void) | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const onAnnouncementRef = useRef(onAnnouncement);
  onAnnouncementRef.current = onAnnouncement;
  const onProgressRef = useRef(onProgress);
  onProgressRef.current = onProgress;
  const lastPlayed = useRef({ day: 0, seq: firstSeq.current - 1 });
  const eventsRef = useRef(events);
  eventsRef.current = events;
  const finaleRef = useRef(finale);
  finaleRef.current = finale;
  const sceneRef = useRef<Phaser.Scene | null>(null);
  const pausedRef = useRef(paused);
  const speedRef = useRef(speed);
  const catchUpRef = useRef(catchUp);
  catchUpRef.current = catchUp;

  useEffect(() => {
    speedRef.current = speed;
    if (sceneRef.current) sceneRef.current.tweens.timeScale = sceneRef.current.time.timeScale = speed;
  }, [speed]);

  useEffect(() => {
    pausedRef.current = paused;
    const s = sceneRef.current;
    if (!s) return;
    s.time.paused = paused;
    if (paused) s.tweens.pauseAll();
    else {
      s.tweens.resumeAll();
      resumePlayback.current?.();
    }
  }, [paused]);

  // A live run's outcome arrives after its last event: if playback is already idle, start the finale.
  useEffect(() => {
    if (finale) resumePlayback.current?.();
  }, [finale]);

  // New events join the queue (only ones not seen yet, in seq order).
  useEffect(() => {
    const fresh = events.filter((e) => e.seq > seen.current).sort((a, b) => a.seq - b.seq);
    if (fresh.length) {
      seen.current = fresh[fresh.length - 1].seq;
      queue.current.push(...fresh);
      resumePlayback.current?.();
    }
  }, [events]);

  useEffect(() => {
    let game: Phaser.Game | undefined;
    let cancelled = false;

    (async () => {
      const PhaserLib = (await import("phaser")).default;
      const EasyStar = (await import("easystarjs")).default;
      if (cancelled || !host.current) return;

      const finder = new EasyStar.js();
      finder.setGrid(walkableGrid());
      finder.setAcceptableTiles([0]);
      finder.enableDiagonals();

      const sprites = new Map<string, Sprite>();
      let busy = false;

      class Garden extends PhaserLib.Scene {
        create() {
          const g = this.add.graphics();
          g.fillStyle(0xeef3e6).fillRect(0, 0, COLS * TILE, ROWS * TILE);
          for (let r = 0; r < ROWS; r++)
            for (let c = 0; c < COLS; c++)
              if (isWall(c, r)) g.fillStyle(0x8b8178).fillRect(c * TILE, r * TILE, TILE, TILE);
          g.fillStyle(0x5a4e44).fillRect(GATE.col * TILE, GATE.rowFrom * TILE, TILE, (GATE.rowTo - GATE.rowFrom + 1) * TILE);
          for (const zone of Object.values(ZONES)) {
            g.fillStyle(zone.color).fillRoundedRect(zone.x * TILE, zone.y * TILE, zone.w * TILE, zone.h * TILE, 6);
            this.add.text(zone.x * TILE + 6, zone.y * TILE + 4, zone.label, { fontSize: "11px", color: "#3b3631" });
          }
          // Where each twin was just before the first event played (home if they hadn't moved yet).
          const placeBefore = new Map<string, Place>();
          for (const e of eventsRef.current)
            if (e.seq < firstSeq.current && e.twin && isPlace(e.place)) placeBefore.set(e.twin, e.place);
          twins.forEach((name, i) => {
            const at = spotFor(placeBefore.get(name) ?? "home", i);
            const body = this.add.circle(at.col * TILE + TILE / 2, at.row * TILE + TILE / 2, 6, COLORS[i % COLORS.length]);
            const label = this.add.text(0, 0, name, { fontSize: "10px", color: "#1f1d1a" }).setOrigin(0.5, 0);
            const emoji = this.add.text(0, 0, "", { fontSize: "12px" }).setOrigin(0.5, 1);
            const bubble = this.add
              .text(0, 0, "", {
                fontSize: "10px",
                color: "#1f1d1a",
                backgroundColor: "#ffffffee",
                padding: { x: 4, y: 2 },
                wordWrap: { width: 140 },
              })
              .setOrigin(0.5, 1)
              .setDepth(10)
              .setVisible(false);
            body.setInteractive({ useHandCursor: true }).on("pointerdown", () => onSelectRef.current?.(name));
            label.setInteractive({ useHandCursor: true }).on("pointerdown", () => onSelectRef.current?.(name));
            const sprite = { body, label, emoji, bubble, at, slot: i };
            sprites.set(name, sprite);
            attachLabels(sprite);
          });
          sceneRef.current = this;
          this.tweens.timeScale = this.time.timeScale = speedRef.current;
          this.time.paused = pausedRef.current;
          resumePlayback.current = () => playNext(this);
          playNext(this);
        }
      }

      function attachLabels(s: Sprite) {
        s.label.setPosition(s.body.x, s.body.y + 7);
        s.emoji.setPosition(s.body.x, s.body.y - 7);
        s.bubble.setPosition(s.body.x, s.body.y - 20);
      }

      let climbed = false;

      /** The breakout scene: the pair meet at the gate, then climb it together and are gone. */
      function climb(scene: Phaser.Scene, pair: [string, string]) {
        const both = pair.map((name) => sprites.get(name)).filter((s): s is Sprite => !!s);
        if (climbed || both.length !== 2) return;
        climbed = true;
        busy = true; // nothing else plays after the breakout
        const midRow = (GATE.rowFrom + GATE.rowTo) / 2;
        both.forEach((s, i) => {
          s.emoji.setText("🧱");
          const row = midRow + (i === 0 ? -1 : 1);
          const atGate = { x: (GATE.col - 1) * TILE + TILE / 2, y: row * TILE + TILE / 2 };
          scene.tweens.chain({
            targets: s.body,
            tweens: [
              { ...atGate, duration: 1400, ease: "Sine.easeInOut" },
              { y: atGate.y - TILE * 1.5, x: GATE.col * TILE + TILE / 2, duration: 700, ease: "Quad.easeOut" }, // up
              { y: atGate.y, x: COLS * TILE + TILE, alpha: 0, duration: 700, ease: "Quad.easeIn" }, // over and out
            ],
            onUpdate: () => {
              attachLabels(s);
              s.label.setAlpha(s.body.alpha);
              s.emoji.setAlpha(s.body.alpha);
            },
          });
        });
      }

      function playNext(scene: Phaser.Scene) {
        if (busy || cancelled || pausedRef.current) return;
        // Announcements become toasts at this point in playback; anything else not drawable is skipped.
        const reached = (e: MapEvent) => {
          lastPlayed.current = { day: e.day, seq: e.seq };
          onProgressRef.current?.({ ...lastPlayed.current, caughtUp: false });
        };
        let next = queue.current.shift();
        while (next && !(next.twin && sprites.has(next.twin) && isPlace(next.place))) {
          reached(next);
          if (next.announcement) onAnnouncementRef.current?.(next);
          next = queue.current.shift();
        }
        if (!next || !next.twin || !isPlace(next.place)) {
          onProgressRef.current?.({ ...lastPlayed.current, caughtUp: true });
          if (finaleRef.current) climb(scene, finaleRef.current);
          return;
        }
        reached(next);
        const s = sprites.get(next.twin)!;
        busy = true;
        s.emoji.setText(next.emoji);
        const line = next.say;
        if (line) {
          s.bubble.setText(line).setVisible(true);
          scene.time.delayedCall(BUBBLE_MS, () => s.bubble.text === line && s.bubble.setVisible(false));
        }
        const target = spotFor(next.place, s.slot);
        finder.findPath(s.at.col, s.at.row, target.col, target.row, (path: { x: number; y: number }[] | null) => {
          if (cancelled) return;
          const steps = path && path.length > 1 ? path.slice(1) : [];
          const pace = catchUpRef.current && queue.current.length > 12 ? 0.3 : 1; // catch up when a live backlog builds
          if (!steps.length) {
            busy = false;
            scene.time.delayedCall(150 * pace, () => playNext(scene));
            return;
          }
          // One tween along the whole path (not one per tile), so 4× isn't held back by per-frame steps.
          const points = [{ x: s.body.x, y: s.body.y }, ...steps.map((p) => ({ x: p.x * TILE + TILE / 2, y: p.y * TILE + TILE / 2 }))];
          scene.tweens.addCounter({
            from: 0,
            to: steps.length,
            duration: STEP_MS * steps.length * pace,
            onUpdate: (tween) => {
              const v = tween.getValue() ?? 0;
              const i = Math.min(Math.floor(v), steps.length - 1);
              const [a, b] = [points[i], points[i + 1]];
              s.body.setPosition(a.x + (b.x - a.x) * (v - i), a.y + (b.y - a.y) * (v - i));
              attachLabels(s);
            },
            onComplete: () => {
              if (cancelled) return;
              s.at = target;
              attachLabels(s);
              busy = false;
              playNext(scene);
            },
          });
        });
        finder.calculate();
      }

      game = new PhaserLib.Game({
        type: PhaserLib.AUTO,
        parent: host.current,
        width: COLS * TILE,
        height: ROWS * TILE,
        backgroundColor: "#eef3e6",
        audio: { noAudio: true }, // silent map; also avoids "closed AudioContext" errors on remount
        scene: Garden,
        scale: { mode: PhaserLib.Scale.FIT, autoCenter: PhaserLib.Scale.CENTER_HORIZONTALLY },
      });
    })();

    return () => {
      cancelled = true;
      resumePlayback.current = null;
      sceneRef.current = null;
      game?.destroy(true);
    };
  }, [twins]);

  return <div ref={host} className="garden-map" data-testid="garden-map" />;
}
