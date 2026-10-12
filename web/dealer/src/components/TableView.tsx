import { SEAT_TILE, SeatTile } from './SeatTile'
import { SUIT_SYMBOL, isRed, rankLabel } from '../lib/cards'
import { money } from '../lib/money'
import { TABLE, feltPath, outlinePath, seatPoses } from '../lib/tableGeometry'
import type { PlayerState } from '../types'

interface TableViewProps {
  players: PlayerState[]
  toAct: number | null
  boards: string[][]
  potTotal: number
}

// Distance from the table edge to the center of a seat tile.
const SEAT_OFFSET = 4 + SEAT_TILE.height / 2
const CARD = { w: 5.6, h: 7.6, gap: 1 } as const

function BoardCard({ code, x, y }: { code: string; x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect width={CARD.w} height={CARD.h} rx={0.8} className="fill-white" />
      <text
        x={CARD.w / 2}
        y={3.8}
        textAnchor="middle"
        className={`text-[3.4px] font-bold ${isRed(code) ? 'fill-red-600' : 'fill-gray-900'}`}
      >
        {rankLabel(code)}
      </text>
      <text
        x={CARD.w / 2}
        y={7}
        textAnchor="middle"
        className={`text-[3px] ${isRed(code) ? 'fill-red-600' : 'fill-gray-900'}`}
      >
        {SUIT_SYMBOL[code[1]]}
      </text>
    </g>
  )
}

export function TableView({ players, toAct, boards, potTotal }: TableViewProps) {
  const poses = seatPoses(players.length)
  const dealerY = TABLE.width / 2 - TABLE.notchDepth / 2
  const rows = boards.filter((b) => b.length > 0)
  const rowTop = rows.length > 1 ? -9.5 : -5.5
  const potY = rows.length > 1 ? -12.2 : -8.4

  return (
    <svg
      viewBox="-68 -42 136 84"
      className="h-full w-full"
      role="group"
      aria-label="Poker table, birds-eye view"
    >
      <path d={outlinePath()} className="fill-stone-700 stroke-stone-400" strokeWidth={0.4} />
      <path d={feltPath()} className="fill-green-800" />

      {potTotal > 0 && (
        <text x={0} y={potY} textAnchor="middle" className="fill-yellow-200 text-[3.2px] font-semibold">
          POT {money(potTotal)}
        </text>
      )}

      {rows.map((row, r) =>
        row.map((code, i) => (
          <BoardCard
            key={`${r}-${code}`}
            code={code}
            x={-((5 * CARD.w + 4 * CARD.gap) / 2) + i * (CARD.w + CARD.gap)}
            y={rowTop + r * (CARD.h + 1.2)}
          />
        )),
      )}

      <text x={0} y={dealerY + 1} textAnchor="middle" className="fill-gray-300 text-[3px]">
        DEALER
      </text>

      {players.map((player, i) => {
        const p = poses[i]
        const bx = p.x + p.nx * (TABLE.rail + 3.2)
        const by = p.y + p.ny * (TABLE.rail + 3.2)
        return (
          <g key={player.seat}>
            {player.bet > 0 && player.status !== 'folded' && (
              <g transform={`translate(${bx} ${by})`}>
                <rect x={-4.2} y={-1.8} width={8.4} height={3.6} rx={1.8} className="fill-gray-900/80 stroke-yellow-300" strokeWidth={0.3} />
                <text y={1} textAnchor="middle" className="fill-yellow-200 text-[2.6px] font-semibold">
                  {money(player.bet)}
                </text>
              </g>
            )}
            <SeatTile
              player={player}
              x={p.x - p.nx * SEAT_OFFSET}
              y={p.y - p.ny * SEAT_OFFSET}
              active={player.seat === toAct}
            />
          </g>
        )
      })}
    </svg>
  )
}
