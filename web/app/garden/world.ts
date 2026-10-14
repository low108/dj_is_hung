// The Garden map: a pixel-art town on a tile grid. Tiles are Kenney's "Tiny Town" (CC0, public/tiles/);
// people and water are drawn in code, so there is no other art licence to track.

export const TILE = 16;
export const COLS = 48;
export const ROWS = 30;

// Must match garden/coordinator.py Place (tests/test_world_places.py checks this file against it).
export const PLACES = ["home", "cafe", "park", "gathering_hall", "coordinator_office", "the_wall"] as const;
export type Place = (typeof PLACES)[number];
// Where a date can be beyond the engine's places (garden/scenes.py DATE_VENUES; checked by the same test).
export const VENUES = ["kitchen", "court", "cinema", "flower_garden", "river", "trail", "bakery", "museum"] as const;
export type Venue = (typeof VENUES)[number];
export type Area = Place | Venue;
export type Tile = { col: number; row: number };

export function isPlace(value: string | null): value is Place {
  return value !== null && (PLACES as readonly string[]).includes(value);
}

export function isArea(value: string | null | undefined): value is Area {
  return !!value && (isPlace(value) || (VENUES as readonly string[]).includes(value));
}

/** Where an event happens on the map: its date venue when the scene pass gave one, else the engine's place. */
export function areaOf(e: { place: string | null; venue?: string | null }): Area | null {
  if (isArea(e.venue)) return e.venue;
  return isPlace(e.place) ? e.place : null;
}

// How an area is drawn. A building has a roof (2 rows), a front wall with a door (1 row) and a yard in
// front where people stand; an open area is ground with a few props.
export type Look =
  | { kind: "building"; roof: "red" | "blue"; wall: "wood" | "stone"; yard: "dirt" | "stone"; units?: number; props?: Prop[] }
  | { kind: "open"; ground: "grass" | "flowers" | "dirt" | "stone" | "water" | "court"; props?: Prop[] };
export type Prop = { col: number; row: number; frame: number }; // relative to the area's top-left

export type Zone = { x: number; y: number; w: number; h: number; label: string; icon: string; look: Look };

// Tiny Town frames (tilemap_packed.png, 12 per row).
export const T = {
  grass: [0, 0, 0, 1], flowers: 2, tree: 16, pine: 28, autumn: 15, bush: 5, mushrooms: 29, sprout: 17,
  dirt: [12, 13, 14, 24, 25, 26, 36, 37, 38], stone: 43, plaza: 109,
  roofRed: [52, 53, 54, 64, 65, 66], roofBlue: [48, 49, 50, 60, 61, 62],
  wallWood: [72, 73, 75], doorWood: 85, windowWood: 84, wallStone: [76, 77, 79], doorStone: 89, windowStone: 88,
  fenceH: 81, fenceL: 80, fenceR: 82, fenceV: 59, sign: 83, target: 95, barrel: 130, bucket: 131, well: 104,
  logs: 106, beehive: 94, lantern: 128, brick: 126,
};

// The town, in three bands with roads between them; the Garden wall runs round the edge with a gate east.
export const ZONES: Record<Area, Zone> = {
  // Top band: where people live, eat and are told what to do.
  home: { x: 2, y: 2, w: 12, h: 7, label: "Homes", icon: "🏠", look: { kind: "building", roof: "blue", wall: "wood", yard: "dirt", units: 3, props: [{ col: 0, row: 6, frame: T.sprout }, { col: 11, row: 6, frame: T.bush }] } },
  bakery: { x: 15, y: 2, w: 7, h: 7, label: "Bakery street", icon: "🥐", look: { kind: "building", roof: "red", wall: "wood", yard: "stone", props: [{ col: 0, row: 3, frame: T.sign }, { col: 6, row: 3, frame: T.barrel }] } },
  cafe: { x: 23, y: 2, w: 7, h: 7, label: "Café", icon: "☕", look: { kind: "building", roof: "blue", wall: "wood", yard: "stone", props: [{ col: 0, row: 3, frame: T.sign }, { col: 6, row: 6, frame: T.bush }] } },
  kitchen: { x: 31, y: 2, w: 7, h: 7, label: "Kitchen", icon: "🍳", look: { kind: "building", roof: "red", wall: "stone", yard: "dirt", props: [{ col: 0, row: 3, frame: T.barrel }, { col: 6, row: 3, frame: T.bucket }, { col: 6, row: 6, frame: T.well }] } },
  coordinator_office: { x: 39, y: 2, w: 7, h: 7, label: "Coordinator", icon: "📋", look: { kind: "building", roof: "blue", wall: "stone", yard: "stone", props: [{ col: 0, row: 3, frame: T.sign }, { col: 6, row: 3, frame: T.lantern }] } },
  // Middle band: the park, the hall where everyone gathers, the stage, the museum, the wall.
  park: { x: 2, y: 11, w: 10, h: 8, label: "Park", icon: "🌳", look: { kind: "open", ground: "grass", props: [{ col: 0, row: 0, frame: T.tree }, { col: 9, row: 0, frame: T.tree }, { col: 0, row: 7, frame: T.pine }, { col: 9, row: 7, frame: T.autumn }, { col: 4, row: 0, frame: T.bush }, { col: 5, row: 7, frame: T.logs }] } },
  gathering_hall: { x: 13, y: 11, w: 11, h: 8, label: "Gathering hall", icon: "🎉", look: { kind: "building", roof: "red", wall: "wood", yard: "stone", props: [{ col: 0, row: 7, frame: T.lantern }, { col: 10, row: 7, frame: T.lantern }] } },
  cinema: { x: 25, y: 11, w: 8, h: 8, label: "Cinema & stage", icon: "🎬", look: { kind: "building", roof: "red", wall: "stone", yard: "dirt", props: [{ col: 0, row: 3, frame: T.sign }, { col: 7, row: 3, frame: T.lantern }] } },
  museum: { x: 34, y: 11, w: 7, h: 8, label: "Museum", icon: "🖼️", look: { kind: "building", roof: "blue", wall: "stone", yard: "stone", props: [{ col: 0, row: 3, frame: T.lantern }, { col: 6, row: 3, frame: T.lantern }] } },
  the_wall: { x: 42, y: 11, w: 5, h: 8, label: "The wall", icon: "🧱", look: { kind: "open", ground: "stone", props: [{ col: 0, row: 1, frame: T.lantern }, { col: 0, row: 7, frame: T.lantern }] } },
  // Bottom band: outdoors.
  court: { x: 2, y: 21, w: 9, h: 7, label: "Sports court", icon: "🏀", look: { kind: "open", ground: "court", props: [{ col: 0, row: 3, frame: T.target }, { col: 8, row: 3, frame: T.target }] } },
  flower_garden: { x: 12, y: 21, w: 8, h: 7, label: "Flower garden", icon: "🌸", look: { kind: "open", ground: "flowers", props: [{ col: 0, row: 0, frame: T.bush }, { col: 7, row: 0, frame: T.beehive }, { col: 7, row: 6, frame: T.bush }] } },
  river: { x: 21, y: 21, w: 11, h: 7, label: "Riverside", icon: "🌊", look: { kind: "open", ground: "water", props: [{ col: 0, row: 0, frame: T.tree }, { col: 10, row: 0, frame: T.pine }] } },
  trail: { x: 33, y: 21, w: 13, h: 7, label: "Hiking trail", icon: "🥾", look: { kind: "open", ground: "dirt", props: [{ col: 0, row: 0, frame: T.pine }, { col: 2, row: 6, frame: T.pine }, { col: 5, row: 0, frame: T.tree }, { col: 8, row: 6, frame: T.autumn }, { col: 11, row: 0, frame: T.pine }, { col: 12, row: 6, frame: T.tree }, { col: 6, row: 6, frame: T.mushrooms }] } },
};

export const WATER_ROWS = 3; // the river runs along the top of the riverside; people stand on the bank below

// The gate in the east wall: where a breakout pair climbs out.
export const GATE = { col: COLS - 1, rowFrom: 13, rowTo: 16 };
export function isWall(col: number, row: number): boolean {
  return col === 0 || row === 0 || col === COLS - 1 || row === ROWS - 1;
}

/** A building's roof and front wall: the rows people can't walk through. */
function isBuildingBody(col: number, row: number): boolean {
  return Object.values(ZONES).some(
    (z) => z.look.kind === "building" && col >= z.x && col < z.x + z.w && row >= z.y && row < z.y + 3,
  );
}

export function isWater(col: number, row: number): boolean {
  const z = ZONES.river;
  return col >= z.x && col < z.x + z.w && row >= z.y && row < z.y + WATER_ROWS;
}

/** Trees and other props block their tile. */
function isProp(col: number, row: number): boolean {
  return Object.values(ZONES).some((z) => (z.look.props ?? []).some((p) => z.x + p.col === col && z.y + p.row === row));
}

export function walkableGrid(): number[][] {
  const grid: number[][] = [];
  for (let r = 0; r < ROWS; r++) {
    grid.push([]);
    for (let c = 0; c < COLS; c++)
      grid[r].push(isWall(c, r) || isBuildingBody(c, r) || isProp(c, r) || isWater(c, r) ? 1 : 0);
  }
  return grid;
}

/** The part of an area where people stand: a building's yard, or an open area inside its border. */
function standing(z: Zone): { x: number; y: number; w: number; h: number } {
  if (z.look.kind === "building") return { x: z.x + 1, y: z.y + 4, w: z.w - 2, h: z.h - 4 };
  if (z.look.ground === "water") return { x: z.x + 1, y: z.y + WATER_ROWS + 1, w: z.w - 2, h: z.h - WATER_ROWS - 2 }; // the bank
  return { x: z.x + 1, y: z.y + 1, w: z.w - 2, h: z.h - 2 };
}

// A stable spot inside an area for each twin, so twins at the same place don't overlap.
export function spotFor(area: Area, slot: number): Tile {
  const s = standing(ZONES[area]);
  const perRow = Math.max(1, Math.floor((s.w + 2) / 3)); // three tiles apart, so names and labels don't overlap
  const col = s.x + (slot % perRow) * 3;
  const row = s.y + Math.floor(slot / perRow) * 2;
  const tile = { col: Math.min(col, s.x + s.w - 1), row: Math.min(row, s.y + s.h - 1) };
  return isProp(tile.col, tile.row) ? { col: tile.col, row: Math.max(s.y, tile.row - 1) } : tile;
}
