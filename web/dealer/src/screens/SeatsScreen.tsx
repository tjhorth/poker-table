import { useState } from 'react'
import { ReturningSheet } from '../components/ReturningSheet'
import { SeatSheet } from '../components/SeatSheet'
import { money, signedMoney } from '../lib/money'
import type { DealerState } from '../types'

function Net({ value }: { value: number }) {
  const tone = value > 0 ? 'text-green-400' : value < 0 ? 'text-red-400' : 'text-gray-400'
  return <span className={`font-semibold ${tone}`}>{value === 0 ? '$0' : signedMoney(value)}</span>
}

// Money per player: everyone at the table by seat, then the players who left.
export function SeatsScreen({ state }: { state: DealerState }) {
  const [seatOpen, setSeatOpen] = useState<number | null>(null)
  const [returningOpen, setReturningOpen] = useState<number | null>(null)
  const seatPlayer = state.players.find((p) => p.seat === seatOpen) ?? null
  const returning = state.inactive.find((p) => p.id === returningOpen) ?? null

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto p-3 text-white">
        <p className="mb-2 px-1 text-sm text-gray-400">
          Tap a seat to edit the player or their stack, or to seat someone in an empty seat.
        </p>
        <table className="w-full border-separate border-spacing-y-2 text-left">
          <thead className="text-xs uppercase tracking-wide text-gray-400">
            <tr>
              <th className="px-4 py-1">Seat</th>
              <th className="px-4 py-1">Player</th>
              <th className="px-4 py-1 text-right">Hands</th>
              <th className="px-4 py-1 text-right">Stack</th>
              <th className="px-4 py-1 text-right">Bought in</th>
              <th className="px-4 py-1 text-right">Net</th>
            </tr>
          </thead>
          <tbody>
            {state.players.map((p) => {
              const empty = p.status === 'empty'
              const onAction = state.phase === 'betting' && state.toAct === p.seat
              return (
                <tr
                  key={p.seat}
                  onClick={() => setSeatOpen(p.seat)}
                  className={`cursor-pointer text-lg active:brightness-125 ${
                    empty
                      ? 'bg-transparent outline-dashed outline-1 outline-gray-600'
                      : onAction
                        ? 'bg-yellow-400/20 outline outline-2 outline-yellow-300'
                        : 'bg-gray-800'
                  }`}
                >
                  <td className="rounded-l-xl px-4 py-3 font-semibold">
                    {p.seat}
                    {p.isButton && (
                      <span className="ml-2 rounded-full bg-yellow-300 px-1.5 text-xs font-bold text-gray-900">
                        D
                      </span>
                    )}
                  </td>
                  {empty ? (
                    <td colSpan={5} className="rounded-r-xl px-4 py-3 text-gray-500">
                      Empty. Tap to seat a player.
                    </td>
                  ) : (
                    <>
                      <td className="px-4 py-3 font-semibold">{p.name}</td>
                      <td className="px-4 py-3 text-right text-gray-300">{p.hands}</td>
                      <td className="px-4 py-3 text-right text-green-400">{money(p.stack)}</td>
                      <td className="px-4 py-3 text-right">{money(p.buyIn)}</td>
                      <td className="rounded-r-xl px-4 py-3 text-right">
                        <Net value={p.net} />
                      </td>
                    </>
                  )}
                </tr>
              )
            })}

            {state.inactive.length > 0 && (
              <>
                <tr>
                  <td colSpan={6} className="px-4 pb-0 pt-4 text-xs uppercase tracking-wide text-gray-500">
                    Not seated
                  </td>
                </tr>
                {state.inactive.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => setReturningOpen(p.id)}
                    className="cursor-pointer bg-gray-800 text-lg opacity-50 active:brightness-125"
                  >
                    <td className="rounded-l-xl px-4 py-3 text-gray-500">—</td>
                    <td className="px-4 py-3 font-semibold">{p.name}</td>
                    <td className="px-4 py-3 text-right">{p.hands}</td>
                    <td className="px-4 py-3 text-right">{money(p.stack)}</td>
                    <td className="px-4 py-3 text-right">{money(p.buyIn)}</td>
                    <td className="rounded-r-xl px-4 py-3 text-right">
                      <Net value={p.net} />
                    </td>
                  </tr>
                ))}
              </>
            )}
          </tbody>
        </table>
      </div>

      {seatPlayer && (
        <SeatSheet
          // a new key resets the sheet's inputs when a different seat or player is opened
          key={`${seatPlayer.seat}-${seatPlayer.name}`}
          player={seatPlayer}
          state={state}
          onClose={() => setSeatOpen(null)}
        />
      )}
      {returning && (
        <ReturningSheet
          key={returning.id}
          player={returning}
          state={state}
          onClose={() => setReturningOpen(null)}
        />
      )}
    </div>
  )
}
