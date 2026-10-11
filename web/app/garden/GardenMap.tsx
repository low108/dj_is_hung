"use client";

import type Phaser from "phaser";
import { useEffect, useRef } from "react";
import { COLS, GATE, ROWS, TILE, ZONES, isPlace, isWall, spotFor, walkableGrid, type Tile } from "./world";

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

const BUBBLE_MS = 2600; // how long a line of speech stays above a twin

type Sprite = {
  body: Phaser.GameObjects.Arc;
  label: Phaser.GameObjects.Text;
  emoji: Phaser.GameObjects.Text;
  bubble: Phaser.GameObjects.Text;
  at: Tile;
  slot: number;
};

const STEP_MS = 90; // per tile while walking
const COLORS = [0xd1495b, 0x2e86ab, 0xf18f01, 0x6a4c93, 0x3d8361, 0x8d6346, 0x247ba0, 0xb5838d];

/** The Garden drawn with Phaser. Plays feed events in order through a queue, walking each twin to
 * the place of its action along an EasyStar path; it speeds up when a live backlog builds.
 * Give it a `key` per simulation: a new run starts with a fresh map, queue and cursor. */
export default function GardenMap({
  events,
  twins,
  onSelect,
  onAnnouncement,
  onProgress,
}: {
  events: MapEvent[];
  twins: string[];
  onSelect?: (twin: string) => void;
  onAnnouncement?: (event: MapEvent) => void; // called when playback reaches it, so toasts match the map
  onProgress?: (day: number, caughtUp: boolean) => void; // the day playback is on; caughtUp when the queue is empty
}) {
  const host = useRef<HTMLDivElement>(null);
  const queue = useRef<MapEvent[]>([]);
  const seen = useRef(-1);
  const resumePlayback = useRef<(() => void) | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const onAnnouncementRef = useRef(onAnnouncement);
  onAnnouncementRef.current = onAnnouncement;
  const onProgressRef = useRef(onProgress);
  onProgressRef.current = onProgress;
  const playingDay = useRef(0);

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
          twins.forEach((name, i) => {
            const at = spotFor("home", i);
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
          resumePlayback.current = () => playNext(this);
          playNext(this);
        }
      }

      function attachLabels(s: Sprite) {
        s.label.setPosition(s.body.x, s.body.y + 7);
        s.emoji.setPosition(s.body.x, s.body.y - 7);
        s.bubble.setPosition(s.body.x, s.body.y - 20);
      }

      function playNext(scene: Phaser.Scene) {
        if (busy || cancelled) return;
        // Announcements become toasts at this point in playback; anything else not drawable is skipped.
        const reached = (e: MapEvent) => {
          playingDay.current = e.day;
          onProgressRef.current?.(e.day, false);
        };
        let next = queue.current.shift();
        while (next && !(next.twin && sprites.has(next.twin) && isPlace(next.place))) {
          reached(next);
          if (next.announcement) onAnnouncementRef.current?.(next);
          next = queue.current.shift();
        }
        if (!next || !next.twin || !isPlace(next.place)) {
          onProgressRef.current?.(playingDay.current, true);
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
          const pace = queue.current.length > 12 ? 0.3 : 1; // catch up when a live backlog builds
          if (!steps.length) {
            busy = false;
            scene.time.delayedCall(150 * pace, () => playNext(scene));
            return;
          }
          scene.tweens.chain({
            targets: s.body,
            tweens: steps.map((p) => ({ x: p.x * TILE + TILE / 2, y: p.y * TILE + TILE / 2, duration: STEP_MS * pace })),
            onUpdate: () => attachLabels(s),
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
        scene: Garden,
        scale: { mode: PhaserLib.Scale.FIT, autoCenter: PhaserLib.Scale.CENTER_HORIZONTALLY },
      });
    })();

    return () => {
      cancelled = true;
      resumePlayback.current = null;
      game?.destroy(true);
    };
  }, [twins]);

  return <div ref={host} className="garden-map" data-testid="garden-map" />;
}
