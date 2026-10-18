"use client";

import type Phaser from "phaser";
import { useEffect, useRef } from "react";
import {
  COLS,
  GATE,
  ROWS,
  T,
  TILE,
  WATER_ROWS,
  ZONES,
  areaOf,
  isWall,
  spotFor,
  walkableGrid,
  type Area,
  type Tile,
  type Zone,
} from "./world";

/** The fields of a feed event (docs/event-contract.md) that the map uses. `venue` and `gist` come from the
 * scene pass over a recorded run (garden/scenes.py): where a date happens, and up to three emoji for a line. */
export type MapEvent = {
  seq: number;
  day: number;
  twin: string | null;
  place: string | null;
  rung?: string | null;
  target?: string | null;
  emoji: string;
  say: string;
  announcement: string | null;
  venue?: string | null;
  gist?: string[];
};

/** Where playback is: the day and seq of the last event played; caughtUp when the queue is empty. */
export type Progress = { day: number; seq: number; caughtUp: boolean };

const BUBBLE_MS = 2600; // how long a speech bubble stays above a twin
const STEP_MS = 110; // per tile while walking, at 1×

// What a twin is doing, under its name (the action label); the emoji badge sits above its head.
const DOING: Record<string, (target: string | null) => string> = {
  talk: (t) => (t ? `talking with ${t}` : "talking"),
  go_to: () => "wandering",
  reflect: () => "reflecting alone",
  seek_out: (t) => (t ? `looking for ${t}` : "looking for someone"),
  check_device: () => "checking the device",
  propose_leaving: (t) => (t ? `asking ${t} to leave` : "asking to leave"),
  go_beyond_wall: (t) => (t ? `at the wall for ${t}` : "at the wall"),
};

// Each twin's look: shirt, hair and skin, picked by its slot.
const SHIRTS = [0xd1495b, 0x2e86ab, 0xf18f01, 0x6a4c93, 0x3d8361, 0x8d6346, 0x247ba0, 0xb5838d];
const HAIR = [0x3b2a20, 0x1f1a17, 0x8a5a2b, 0xd9a441, 0x5c3a21, 0x2b2b2b, 0xa0522d, 0x4a3426];
const SKIN = [0xf1c27d, 0xe0ac69, 0xc68642, 0xffdbac, 0x8d5524, 0xf1c27d, 0xe0ac69, 0xffdbac];

type Sprite = {
  body: Phaser.GameObjects.Image;
  name: Phaser.GameObjects.Text;
  doing: Phaser.GameObjects.Text;
  badge: Phaser.GameObjects.Text;
  bubble: Phaser.GameObjects.Text;
  at: Tile;
  slot: number;
  area: Area;
  spot: number; // which spot in its area it holds
};

/** The Garden drawn with Phaser as a pixel-art town. Plays feed events in order through a queue, walking
 * each twin to the area of its action along an EasyStar path; with `catchUp` it hurries through a live
 * backlog. `speed` scales every walk and timer; `paused` freezes playback where it is.
 * `startAt` begins playback at that seq, with each twin already where the events before it left them.
 * `finale` (a breakout pair) climbs the gate together once the last event has played.
 * `woman` is drawn in a dress. Give it a `key` per simulation, replay or jump: each starts fresh. */
export default function GardenMap({
  events,
  twins,
  woman = null,
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
  woman?: string | null;
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
  const womanRef = useRef(woman);
  womanRef.current = woman;
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
        preload() {
          this.load.spritesheet("town", "/tiles/tiny-town.png", { frameWidth: TILE, frameHeight: TILE });
        }

        create() {
          drawTown(this);
          // Where each twin was just before the first event played (home if they hadn't moved yet).
          const areaBefore = new Map<string, Area>();
          for (const e of eventsRef.current) {
            const area = areaOf(e);
            if (e.seq < firstSeq.current && e.twin && area) areaBefore.set(e.twin, area);
          }
          twins.forEach((name, i) => {
            const startArea = areaBefore.get(name) ?? "home";
            const startSpot = freeSpot(startArea);
            const at = spotFor(startArea, startSpot);
            const texture = drawPerson(this, i, name === womanRef.current);
            const body = this.add.image(at.col * TILE + TILE / 2, at.row * TILE + TILE / 2, texture).setDepth(5);
            const label = (text: string, size: string, color: string, style = "bold") =>
              this.add
                .text(0, 0, text, { fontSize: size, color, fontStyle: style, fontFamily: "monospace", resolution: 3 })
                .setOrigin(0.5, 0)
                .setDepth(6)
                .setStroke("#ffffff", 3);
            const name_ = label(name, "8px", "#1f1d1a");
            const doing = label("", "7px", "#5a514a", "italic");
            const badge = this.add
              .text(0, 0, "", { fontSize: "11px", backgroundColor: "#fffffff0", padding: { x: 2, y: 1 }, resolution: 3 })
              .setOrigin(0.5, 1)
              .setDepth(7)
              .setVisible(false);
            const bubble = this.add
              .text(0, 0, "", { fontSize: "12px", backgroundColor: "#fffdf4f5", padding: { x: 4, y: 2 }, resolution: 3 })
              .setOrigin(0.5, 1)
              .setDepth(8)
              .setVisible(false);
            for (const o of [body, name_]) o.setInteractive({ useHandCursor: true }).on("pointerdown", () => onSelectRef.current?.(name));
            const sprite = { body, name: name_, doing, badge, bubble, at, slot: i, area: startArea, spot: startSpot };
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

      /** The first spot in an area nobody else holds: whoever arrives first stands first, so a date pair
       * ends up side by side rather than wherever their fixed slots happen to be. */
      function freeSpot(area: Area, except?: string): number {
        const held = new Set([...sprites].filter(([n, s]) => n !== except && s.area === area).map(([, s]) => s.spot));
        let spot = 0;
        while (held.has(spot)) spot++;
        return spot;
      }

      function attachLabels(s: Sprite) {
        const { x, y } = s.body;
        s.name.setPosition(x, y + 8);
        s.doing.setPosition(x, y + 16);
        s.badge.setPosition(x, y - 9);
        s.bubble.setPosition(x, y - (s.badge.text ? 22 : 10));
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
          s.badge.setText("🧱");
          s.doing.setText("going beyond the wall");
          s.bubble.setText("❤️🤝🧱").setVisible(true);
          const row = midRow + (i === 0 ? -0.5 : 0.5); // side by side, hand in hand
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
              for (const o of [s.name, s.doing, s.badge, s.bubble]) o.setAlpha(s.body.alpha);
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
        while (next && !(next.twin && sprites.has(next.twin) && areaOf(next))) {
          reached(next);
          if (next.announcement) onAnnouncementRef.current?.(next);
          next = queue.current.shift();
        }
        const area = next ? areaOf(next) : null;
        if (!next || !next.twin || !area) {
          onProgressRef.current?.({ ...lastPlayed.current, caughtUp: true });
          if (finaleRef.current) climb(scene, finaleRef.current);
          return;
        }
        reached(next);
        const s = sprites.get(next.twin)!;
        busy = true;
        s.badge.setText(next.emoji).setVisible(!!next.emoji);
        const doing = next.rung ? (DOING[next.rung]?.(next.target ?? null) ?? "") : "";
        // One action label at a time (the latest): side by side, two labels run into each other.
        for (const other of sprites.values()) if (other !== s) other.doing.setVisible(false);
        s.doing.setText(doing).setVisible(true);
        scene.time.delayedCall(BUBBLE_MS * 1.5, () => s.doing.text === doing && s.doing.setVisible(false));
        // The bubble sums the line up in up to three emoji; the words themselves are in her log.
        const gist = next.gist?.length ? next.gist.join("") : next.say ? "💬" : "";
        if (gist) {
          s.bubble.setText(gist).setVisible(true);
          scene.time.delayedCall(BUBBLE_MS, () => s.bubble.text === gist && s.bubble.setVisible(false));
        }
        attachLabels(s);
        if (s.area !== area) {
          s.spot = freeSpot(area, next.twin);
          s.area = area;
        }
        const target = spotFor(area, s.spot);
        finder.findPath(s.at.col, s.at.row, target.col, target.row, (path: { x: number; y: number }[] | null) => {
          if (cancelled) return;
          const steps = path && path.length > 1 ? path.slice(1) : [];
          const pace = catchUpRef.current && queue.current.length > 12 ? 0.3 : 1; // catch up when a live backlog builds
          if (!steps.length) {
            busy = false;
            scene.time.delayedCall(500 * pace, () => playNext(scene)); // a beat to read the bubble
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
              const bob = Math.abs(Math.sin(v * Math.PI)) * 1.5; // a step's bounce
              s.body.setPosition(a.x + (b.x - a.x) * (v - i), a.y + (b.y - a.y) * (v - i) - bob);
              if (b.x !== a.x) s.body.setFlipX(b.x < a.x);
              attachLabels(s);
            },
            onComplete: () => {
              if (cancelled) return;
              s.at = target;
              s.body.setPosition(target.col * TILE + TILE / 2, target.row * TILE + TILE / 2);
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
        backgroundColor: "#8cc56a",
        pixelArt: true,
        audio: { noAudio: true }, // silent map; also avoids "closed AudioContext" errors on remount
        scene: Garden,
        scale: { mode: PhaserLib.Scale.FIT, autoCenter: PhaserLib.Scale.CENTER_HORIZONTALLY },
      });
      // In development, the console can reach the map (e.g. zoom the camera on a scene to check it).
      if (process.env.NODE_ENV === "development") (window as unknown as { garden?: Phaser.Game }).garden = game;
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

/** The town: grass, roads, every area, the Garden wall and its gate. */
function drawTown(scene: Phaser.Scene) {
  const tile = (col: number, row: number, frame: number, depth = 0) =>
    scene.add.image(col * TILE + TILE / 2, row * TILE + TILE / 2, "town", frame).setDepth(depth);
  // Grass everywhere, a little varied; roads between the bands and down the middle.
  for (let r = 0; r < ROWS; r++)
    for (let c = 0; c < COLS; c++) tile(c, r, T.grass[(c * 7 + r * 13) % T.grass.length]);
  for (let c = 1; c < COLS - 1; c++) for (const r of [9, 10, 19, 20]) tile(c, r, 25);
  for (let r = 1; r < ROWS - 1; r++) tile(1, r, 25);
  for (const z of Object.values(ZONES)) drawZone(scene, z, tile);
  // The Garden wall all round, with the gate in the east wall.
  for (let r = 0; r < ROWS; r++)
    for (let c = 0; c < COLS; c++)
      if (isWall(c, r)) tile(c, r, c === GATE.col && r >= GATE.rowFrom && r <= GATE.rowTo ? 103 : T.brick, 1);
}

function drawZone(scene: Phaser.Scene, z: Zone, tile: (c: number, r: number, f: number, d?: number) => Phaser.GameObjects.Image) {
  const look = z.look;
  const right = z.x + z.w - 1;
  if (look.kind === "building") {
    const roof = look.roof === "red" ? T.roofRed : T.roofBlue;
    const [wl, wm, wr] = look.wall === "wood" ? T.wallWood : T.wallStone;
    const door = look.wall === "wood" ? T.doorWood : T.doorStone;
    const window_ = look.wall === "wood" ? T.windowWood : T.windowStone;
    const units = look.units ?? 1;
    const width = Math.floor(z.w / units);
    for (let u = 0; u < units; u++) {
      const left = z.x + u * width;
      const end = u === units - 1 ? right : left + width - 1;
      const mid = left + Math.floor((end - left + 1) / 2);
      for (let c = left; c <= end; c++) {
        const edge = c === left ? 0 : c === end ? 2 : 1;
        tile(c, z.y, roof[edge]);
        tile(c, z.y + 1, roof[3 + edge]);
        const wall = c === mid ? door : c === left ? wl : c === end ? wr : (c - left) % 3 === 1 ? window_ : wm;
        tile(c, z.y + 2, wall);
      }
      // A path from each door down through the yard (stone or dirt); the rest of the yard is grass.
      for (let r = z.y + 3; r < z.y + z.h; r++) tile(mid, r, look.yard === "stone" ? T.stone : 25);
    }
  } else if (look.ground === "water") {
    const g = scene.add.graphics();
    g.fillStyle(0x4aa3df).fillRect(z.x * TILE, z.y * TILE, z.w * TILE, WATER_ROWS * TILE);
    g.fillStyle(0x7cc4f0);
    for (let i = 0; i < z.w * 2; i++) g.fillRect(z.x * TILE + i * 8 + ((i * 5) % 7), z.y * TILE + 6 + ((i * 11) % 30), 5, 2);
    g.fillStyle(0xd9c27a).fillRect(z.x * TILE, (z.y + WATER_ROWS) * TILE, z.w * TILE, 3); // sandy edge
  } else {
    for (let c = z.x; c <= right; c++)
      for (let r = z.y; r < z.y + z.h; r++) {
        if (look.ground === "flowers") tile(c, r, (c + r) % 2 ? T.flowers : 1);
        else if (look.ground === "stone") tile(c, r, T.stone);
        else if (look.ground === "court") tile(c, r, 25);
        else if (look.ground === "dirt") {
          const pathRow = z.y + 2 + Math.round(1.5 + 1.5 * Math.sin((c - z.x) / 2)); // a winding trail
          tile(c, r, r === pathRow || r === pathRow + 1 ? 25 : (c * 3 + r) % 7 === 0 ? 1 : 0);
        }
      }
    if (look.ground === "court") {
      const g = scene.add.graphics().lineStyle(1, 0xffffff, 0.9);
      g.strokeRect(z.x * TILE + 4, z.y * TILE + 4, z.w * TILE - 8, z.h * TILE - 8);
      g.lineBetween((z.x + z.w / 2) * TILE, z.y * TILE + 4, (z.x + z.w / 2) * TILE, (z.y + z.h) * TILE - 4);
      g.strokeCircle((z.x + z.w / 2) * TILE, (z.y + z.h / 2) * TILE, TILE);
    }
    if (look.ground === "flowers") {
      for (let c = z.x; c <= right; c++) tile(c, z.y + z.h, c === z.x ? T.fenceL : c === right ? T.fenceR : T.fenceH, 1);
    }
  }
  for (const p of look.props ?? []) tile(z.x + p.col, z.y + p.row, p.frame, 2);
  // The area's name on a sign-like label at its top-left.
  scene.add
    .text(z.x * TILE + 2, z.y * TILE + 1, `${z.icon} ${z.label}`, {
      fontSize: "8px",
      color: "#ffffff",
      backgroundColor: "#3b3631cc",
      padding: { x: 2, y: 1 },
      fontFamily: "monospace",
      resolution: 3,
    })
    .setDepth(4);
}

/** A 12×16 pixel person drawn in code (no character art to license): hair, face, shirt or dress, legs. */
function drawPerson(scene: Phaser.Scene, slot: number, dress: boolean): string {
  const key = `person-${slot}-${dress ? "f" : "m"}`;
  if (scene.textures.exists(key)) return key;
  const g = scene.make.graphics({ x: 0, y: 0 }, false);
  const px = (x: number, y: number, w: number, h: number, color: number) => g.fillStyle(color).fillRect(x, y, w, h);
  const shirt = SHIRTS[slot % SHIRTS.length];
  const hair = HAIR[slot % HAIR.length];
  const skin = SKIN[slot % SKIN.length];
  px(3, 1, 6, 2, hair); // hair on top
  px(3, 3, 6, 4, skin); // face
  px(4, 4, 1, 1, 0x1f1a17); // eyes
  px(7, 4, 1, 1, 0x1f1a17);
  if (dress) {
    px(2, 2, 1, 6, hair); // long hair down both sides
    px(9, 2, 1, 6, hair);
    px(3, 7, 6, 4, shirt); // bodice
    px(2, 11, 8, 3, shirt); // skirt
    px(4, 14, 1, 2, skin); // legs
    px(7, 14, 1, 2, skin);
  } else {
    px(3, 2, 1, 2, hair);
    px(8, 2, 1, 2, hair);
    px(3, 7, 6, 5, shirt); // shirt
    px(2, 8, 1, 3, skin); // arms
    px(9, 8, 1, 3, skin);
    px(3, 12, 6, 2, 0x3a4a6b); // trousers
    px(3, 14, 2, 2, 0x2b2b2b); // shoes
    px(7, 14, 2, 2, 0x2b2b2b);
  }
  g.generateTexture(key, 12, 16);
  g.destroy();
  return key;
}
