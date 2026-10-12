type SeatTileProps = {
  seat: number
  player: string | null
  // center of the tile in table units
  x: number
  y: number
  onSelect?: (seat: number) => void
}

export const SEAT_TILE = { width: 17, height: 11 } as const

export function SeatTile({ seat, player, x, y, onSelect }: SeatTileProps) {
  const select = () => onSelect?.(seat)

  return (
    <g
      className="group cursor-pointer outline-none"
      transform={`translate(${x - SEAT_TILE.width / 2} ${y - SEAT_TILE.height / 2})`}
      role="button"
      tabIndex={0}
      aria-label={`Seat ${seat}, ${player ?? 'empty'}`}
      onClick={select}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') select()
      }}
    >
      <rect
        width={SEAT_TILE.width}
        height={SEAT_TILE.height}
        rx={1.5}
        className="fill-gray-800 stroke-white transition-colors duration-200 group-hover:fill-white group-focus-visible:stroke-yellow-300"
        strokeWidth={0.4}
      />
      <text
        x={SEAT_TILE.width / 2}
        y={4.6}
        textAnchor="middle"
        className="fill-white text-[3.2px] font-medium group-hover:fill-gray-800"
      >
        SEAT {seat}
      </text>
      <text
        x={SEAT_TILE.width / 2}
        y={8.4}
        textAnchor="middle"
        className={`text-[2.9px] ${player ? 'fill-green-500' : 'fill-red-400'}`}
      >
        {player ?? 'EMPTY'}
      </text>
    </g>
  )
}
