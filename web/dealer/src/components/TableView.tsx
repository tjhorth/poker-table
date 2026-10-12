import { SEAT_TILE, SeatTile } from './SeatTile'
import { TABLE, feltPath, outlinePath, seatPoses } from '../lib/tableGeometry'

export type SeatInfo = {
  seat: number
  player: string | null
}

type TableViewProps = {
  seats: SeatInfo[]
  onSelect?: (seat: number) => void
}

// Distance from the table edge to the center of a seat tile.
const SEAT_OFFSET = 4 + SEAT_TILE.height / 2

export function TableView({ seats, onSelect }: TableViewProps) {
  const poses = seatPoses(seats.length)
  const dealerY = TABLE.width / 2 - TABLE.notchDepth / 2

  return (
    <svg
      viewBox="-68 -42 136 84"
      className="h-full w-full"
      role="group"
      aria-label="Poker table, birds-eye view"
    >
      <path d={outlinePath()} className="fill-stone-700 stroke-stone-400" strokeWidth={0.4} />
      <path d={feltPath()} className="fill-green-800" />

      <rect
        x={-12}
        y={-6}
        width={24}
        height={9}
        rx={1}
        className="fill-none stroke-green-600"
        strokeWidth={0.3}
        strokeDasharray="1 1"
      />
      <text x={0} y={-0.5} textAnchor="middle" className="fill-green-500 text-[3px]">
        BOARD
      </text>

      <text x={0} y={dealerY + 1} textAnchor="middle" className="fill-gray-300 text-[3px]">
        DEALER
      </text>

      {seats.map((s, i) => {
        const p = poses[i]
        return (
          <SeatTile
            key={s.seat}
            seat={s.seat}
            player={s.player}
            x={p.x - p.nx * SEAT_OFFSET}
            y={p.y - p.ny * SEAT_OFFSET}
            onSelect={onSelect}
          />
        )
      })}
    </svg>
  )
}
