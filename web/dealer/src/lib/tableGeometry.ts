// Birds-eye table geometry in SVG units (1 unit = 1 inch, y grows downward).
// The dealer sits at the bottom, inside a notch cut into the long edge.

export const TABLE = {
  length: 90,
  width: 46,
  rail: 4.5,
  notchWidth: 30,
  notchDepth: 12,
  notchRadius: 4,
} as const

const R = TABLE.width / 2
const A = (TABLE.length - TABLE.width) / 2
const HALF_NOTCH = TABLE.notchWidth / 2
const STRAIGHT_BOTTOM = A - HALF_NOTCH
const ARC = Math.PI * R
const STRAIGHT_TOP = 2 * A

export const PERIMETER = 2 * STRAIGHT_BOTTOM + 2 * ARC + STRAIGHT_TOP

export type Pose = {
  x: number
  y: number
  // inward-facing unit normal
  nx: number
  ny: number
}

// Walks the outer edge clockwise (on screen) from the left end of the dealer
// notch: left along the bottom, up the left cap, across the top, down the
// right cap, and back along the bottom to the right end of the notch.
function poseAt(distance: number): Pose {
  let s = distance

  if (s < STRAIGHT_BOTTOM) {
    return { x: -HALF_NOTCH - s, y: R, nx: 0, ny: -1 }
  }
  s -= STRAIGHT_BOTTOM

  if (s < ARC) {
    const t = Math.PI / 2 + s / R
    return { x: -A + R * Math.cos(t), y: R * Math.sin(t), nx: -Math.cos(t), ny: -Math.sin(t) }
  }
  s -= ARC

  if (s < STRAIGHT_TOP) {
    return { x: -A + s, y: -R, nx: 0, ny: 1 }
  }
  s -= STRAIGHT_TOP

  if (s < ARC) {
    const t = (3 * Math.PI) / 2 + s / R
    return { x: A + R * Math.cos(t), y: R * Math.sin(t), nx: -Math.cos(t), ny: -Math.sin(t) }
  }
  s -= ARC

  return { x: A - s, y: R, nx: 0, ny: -1 }
}

// Seat 1 is the first seat to the dealer's left; numbering runs clockwise.
export function seatPoses(count: number): Pose[] {
  const pitch = PERIMETER / count
  return Array.from({ length: count }, (_, i) => poseAt((i + 0.5) * pitch))
}

function round(n: number) {
  return Math.round(n * 100) / 100
}

// Outer table outline (rail) including the dealer notch.
export function outlinePath(): string {
  const { notchDepth: d, notchRadius: r } = TABLE
  const n = HALF_NOTCH
  return [
    `M ${-n} ${R}`,
    `L ${-A} ${R}`,
    `A ${R} ${R} 0 0 1 ${-A} ${-R}`,
    `L ${A} ${-R}`,
    `A ${R} ${R} 0 0 1 ${A} ${R}`,
    `L ${n} ${R}`,
    `L ${n} ${round(R - d + r)}`,
    `A ${r} ${r} 0 0 0 ${round(n - r)} ${R - d}`,
    `L ${round(-n + r)} ${R - d}`,
    `A ${r} ${r} 0 0 0 ${-n} ${round(R - d + r)}`,
    'Z',
  ].join(' ')
}

// Playing surface (felt): the outline inset by the rail width.
export function feltPath(): string {
  const { rail: w, notchDepth: d } = TABLE
  const r = R - w
  const n = HALF_NOTCH + w
  const top = R - d - w
  const c = 6
  return [
    `M ${-n} ${r}`,
    `L ${-A} ${r}`,
    `A ${r} ${r} 0 0 1 ${-A} ${-r}`,
    `L ${A} ${-r}`,
    `A ${r} ${r} 0 0 1 ${A} ${r}`,
    `L ${n} ${r}`,
    `L ${n} ${top + c}`,
    `A ${c} ${c} 0 0 0 ${n - c} ${top}`,
    `L ${-n + c} ${top}`,
    `A ${c} ${c} 0 0 0 ${-n} ${top + c}`,
    'Z',
  ].join(' ')
}
