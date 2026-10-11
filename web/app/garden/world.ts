// The Garden map: a tile grid, the zones twins move between, and walkable tiles for pathfinding.
// Drawn with shapes in code (no third-party tileset), so there is no art licence to track.

export const TILE = 16;
export const COLS = 40;
export const ROWS = 26;

// Must match garden/coordinator.py Place (tests/test_world_places.py checks this file against it).
export const PLACES = ["home", "cafe", "park", "gathering_hall", "coordinator_office", "the_wall"] as const;
export type Place = (typeof PLACES)[number];
export type Tile = { col: number; row: number };

export function isPlace(value: string | null): value is Place {
  return value !== null && (PLACES as readonly string[]).includes(value);
}

export type Zone = { x: number; y: number; w: number; h: number; label: string; color: number };

// Every place in the event contract (garden/coordinator.py Place) has a zone.
export const ZONES: Record<Place, Zone> = {
  home: { x: 3, y: 3, w: 12, h: 6, label: "Homes", color: 0xe9d8b4 },
  cafe: { x: 18, y: 3, w: 8, h: 6, label: "Café", color: 0xf2c6a0 },
  coordinator_office: { x: 29, y: 3, w: 8, h: 6, label: "Coordinator", color: 0xc9cfd8 },
  park: { x: 3, y: 13, w: 14, h: 9, label: "Park", color: 0xb8dba8 },
  gathering_hall: { x: 20, y: 13, w: 10, h: 9, label: "Gathering hall", color: 0xd9c2e6 },
  the_wall: { x: COLS - 5, y: 13, w: 4, h: 9, label: "The wall", color: 0xbfb6a8 }, // flush against the east wall
};

// The stone wall runs around the edge. "The wall" zone sits flush against its east side, where a gate
// is drawn: that's where twins go to cross.
export const GATE = { col: COLS - 1, rowFrom: 15, rowTo: 19 };
export function isWall(col: number, row: number): boolean {
  return col === 0 || row === 0 || col === COLS - 1 || row === ROWS - 1;
}

export function walkableGrid(): number[][] {
  const grid: number[][] = [];
  for (let r = 0; r < ROWS; r++) {
    grid.push([]);
    for (let c = 0; c < COLS; c++) grid[r].push(isWall(c, r) ? 1 : 0);
  }
  return grid;
}

// A stable spot inside a zone for each twin, so twins at the same place don't overlap.
export function spotFor(place: Place, slot: number): Tile {
  const z = ZONES[place];
  const perRow = Math.max(1, Math.floor((z.w - 2) / 2));
  const col = z.x + 1 + (slot % perRow) * 2;
  const row = z.y + 2 + Math.floor(slot / perRow) * 2;
  return { col: Math.min(col, z.x + z.w - 2), row: Math.min(row, z.y + z.h - 2) };
}
