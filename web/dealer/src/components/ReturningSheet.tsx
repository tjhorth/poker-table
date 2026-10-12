import { useState } from 'react'
import { send } from '../api/socket'
import { money, signedMoney } from '../lib/money'
import type { DealerState, InactivePlayer } from '../types'

interface Props {
  player: InactivePlayer
  state: DealerState
  onClose: () => void
}

// Seats a player who left earlier, from their row in the money list.
export function ReturningSheet({ player, state, onClose }: Props) {
  const open = state.players.filter((p) => p.status === 'empty').map((p) => p.seat)
  const [seat, setSeat] = useState<number | null>(open[0] ?? null)
  const [stack, setStack] = useState(String(player.stack))
  const stackN = Number(stack) || 0
  const diff = stackN - player.stack
  const netTone = player.net > 0 ? 'text-green-400' : player.net < 0 ? 'text-red-400' : 'text-gray-300'

  return (
    <div className="absolute inset-0 z-20 flex items-end justify-center bg-black/70 p-3 lg:items-center">
      <section
        role="dialog"
        aria-modal="true"
        aria-label={`Seat ${player.name}`}
        className="flex max-h-full w-full max-w-xl flex-col overflow-hidden rounded-2xl bg-gray-800 text-white shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-gray-700 px-5 py-4">
          <h2 className="text-2xl font-bold">{player.name}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-gray-700 px-4 py-2 font-medium active:bg-gray-600"
          >
            Close
          </button>
        </header>

        <div className="space-y-4 overflow-y-auto p-5">
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-xl bg-gray-900 px-3 py-2">
              <div className="text-xs uppercase tracking-wide text-gray-400">Left with</div>
              <div className="text-xl font-bold">{money(player.stack)}</div>
            </div>
            <div className="rounded-xl bg-gray-900 px-3 py-2">
              <div className="text-xs uppercase tracking-wide text-gray-400">Bought in</div>
              <div className="text-xl font-bold">{money(player.buyIn)}</div>
            </div>
            <div className="rounded-xl bg-gray-900 px-3 py-2">
              <div className="text-xs uppercase tracking-wide text-gray-400">Net</div>
              <div className={`text-xl font-bold ${netTone}`}>
                {player.net === 0 ? '$0' : signedMoney(player.net)}
              </div>
            </div>
          </div>

          {open.length === 0 ? (
            <p className="text-yellow-300">
              Every seat is taken. Remove a player from a seat to make room.
            </p>
          ) : (
            <>
              <div>
                <div className="mb-1 text-sm text-gray-300">Seat</div>
                <div className="flex flex-wrap gap-2">
                  {open.map((s) => (
                    <button
                      key={s}
                      type="button"
                      aria-pressed={seat === s}
                      onClick={() => setSeat(s)}
                      className={`min-h-12 min-w-16 rounded-xl px-4 text-lg font-semibold ${
                        seat === s ? 'bg-yellow-400 text-gray-900' : 'bg-gray-700 active:bg-gray-600'
                      }`}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              <label className="block">
                <span className="mb-1 block text-sm text-gray-300">Stack to sit down with</span>
                <input
                  inputMode="numeric"
                  value={stack}
                  onChange={(e) => setStack(e.target.value.replace(/[^0-9]/g, ''))}
                  className="min-h-12 w-full rounded-lg bg-gray-900 px-3 text-xl outline-none"
                />
              </label>

              {diff !== 0 && stackN > 0 && (
                <p className="text-sm text-gray-300">
                  {diff > 0
                    ? `${money(diff)} more than they left with: counted as an add-on.`
                    : `${money(-diff)} less than they left with: counted as chips taken off the table.`}
                </p>
              )}
              {!state.canEditStacks && (
                <p className="text-sm text-yellow-300">Players can be seated between hands.</p>
              )}

              <button
                type="button"
                disabled={!state.canEditStacks || seat === null || stackN <= 0}
                onClick={() => {
                  if (seat !== null) send({ cmd: 'seat_returning', seat, id: player.id, stack: stackN })
                  onClose()
                }}
                className="min-h-14 w-full rounded-xl bg-green-500 text-xl font-bold text-gray-900 active:bg-green-400 disabled:bg-gray-600 disabled:text-gray-400"
              >
                Seat {player.name}
                {seat !== null ? ` in seat ${seat}` : ''}
              </button>
            </>
          )}
        </div>
      </section>
    </div>
  )
}
