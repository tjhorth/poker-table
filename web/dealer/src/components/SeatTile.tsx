import { money } from '../lib/money'
import type { PlayerState } from '../types'

export const SEAT_TILE = { width: 18, height: 11.5 } as const

interface SeatTileProps {
  player: PlayerState
  x: number // center of the tile, in table units
  y: number
  active: boolean
}

export function SeatTile({ player, x, y, active }: SeatTileProps) {
  if (player.status === 'empty') {
    return (
      <g
        transform={`translate(${x - SEAT_TILE.width / 2} ${y - SEAT_TILE.height / 2})`}
        role="group"
        aria-label={`Seat ${player.seat}, empty`}
      >
        <rect
          width={SEAT_TILE.width}
          height={SEAT_TILE.height}
          rx={1.5}
          className="fill-transparent stroke-gray-500"
          strokeWidth={0.3}
          strokeDasharray="1 1"
        />
        <text x={1.2} y={3.2} className="fill-gray-500 text-[2.1px]">
          S{player.seat}
        </text>
        <text x={SEAT_TILE.width / 2} y={7} textAnchor="middle" className="fill-gray-500 text-[2.8px]">
          EMPTY
        </text>
      </g>
    )
  }

  const folded = player.status === 'folded'
  const caption = folded ? 'FOLDED' : player.status === 'all_in' ? 'ALL-IN' : player.lastAction
  const captionColor = folded
    ? 'fill-gray-400'
    : player.status === 'all_in'
      ? 'fill-red-400'
      : 'fill-sky-300'

  return (
    <g
      transform={`translate(${x - SEAT_TILE.width / 2} ${y - SEAT_TILE.height / 2})`}
      className={`transition-opacity duration-300 ${folded ? 'opacity-40' : ''}`}
      role="group"
      aria-label={`Seat ${player.seat}, ${player.name ?? 'empty'}, ${money(player.stack)}${
        active ? ', on action' : ''
      }`}
    >
      <rect
        width={SEAT_TILE.width}
        height={SEAT_TILE.height}
        rx={1.5}
        className={`fill-gray-800 transition-colors duration-300 ${
          active ? 'stroke-yellow-300' : 'stroke-white/60'
        }`}
        strokeWidth={active ? 0.9 : 0.35}
      />
      <text x={1.2} y={3.2} className="fill-gray-400 text-[2.1px]">
        S{player.seat}
      </text>
      <text
        x={SEAT_TILE.width / 2}
        y={5.6}
        textAnchor="middle"
        className="fill-white text-[3.3px] font-semibold"
      >
        {player.name ?? 'EMPTY'}
      </text>
      <text
        x={SEAT_TILE.width / 2}
        y={8.5}
        textAnchor="middle"
        className="fill-green-400 text-[3px] font-medium"
      >
        {money(player.stack)}
      </text>
      {caption && (
        <text
          x={SEAT_TILE.width / 2}
          y={10.6}
          textAnchor="middle"
          className={`${captionColor} text-[2.1px] font-semibold`}
        >
          {caption}
        </text>
      )}

      {/* registered hole cards, as small card backs */}
      {Array.from({ length: player.cards }, (_, i) => (
        <rect
          key={i}
          x={SEAT_TILE.width - 2.2 - i * 1.9}
          y={1.1}
          width={1.5}
          height={2.1}
          rx={0.3}
          className="fill-blue-500"
        />
      ))}

      {player.isButton && (
        <g>
          <circle cx={0.4} cy={0.4} r={1.9} className="fill-yellow-300" />
          <text x={0.4} y={1.3} textAnchor="middle" className="fill-gray-900 text-[2.4px] font-bold">
            D
          </text>
        </g>
      )}
    </g>
  )
}
