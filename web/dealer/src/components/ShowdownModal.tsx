import { CardRow } from './CardChip'
import { money, signedMoney } from '../lib/money'
import type { DealerState, ShowdownPlayer } from '../types'

interface Props {
  state: DealerState
  disabled: boolean
  onNextHand: () => void
  onHide: () => void
}

const RESULT_STYLE: Record<ShowdownPlayer['result'], string> = {
  win: 'bg-green-500 text-gray-900',
  split: 'bg-yellow-400 text-gray-900',
  lose: 'bg-gray-600 text-gray-200',
}
const RESULT_LABEL: Record<ShowdownPlayer['result'], string> = {
  win: 'WINNER',
  split: 'SPLIT',
  lose: 'LOST',
}

export function ShowdownModal({ state, disabled, onNextHand, onHide }: Props) {
  const result = state.showdown
  if (!result) return null
  const name = (seat: number) => state.players.find((p) => p.seat === seat)?.name ?? `Seat ${seat}`
  const totalPot = result.pots.reduce((sum, p) => sum + p.amount, 0)
  const multiBoard = result.boards.length > 1

  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/70 p-3">
      <section
        className="flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-gray-800 text-white shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label="Showdown result"
      >
        <header className="flex items-start justify-between gap-4 border-b border-gray-700 px-5 py-4">
          <div>
            <h2 className="text-2xl font-bold">{result.contested ? 'Showdown' : 'Pot awarded'}</h2>
            <p className="text-sm text-gray-300">
              Hand #{state.hand} · {state.gameLabel} · Blinds {state.blinds} · Pot {money(totalPot)}
            </p>
          </div>
          <button
            type="button"
            onClick={onHide}
            className="rounded-lg bg-gray-700 px-4 py-2 text-sm font-medium active:bg-gray-600"
          >
            View table
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {result.contested && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
              <span className="text-sm font-medium uppercase tracking-wide text-gray-400">
                {multiBoard ? 'Boards' : 'Board'}
              </span>
              {result.boards.map((b, i) => (
                <CardRow key={i} cards={b} />
              ))}
            </div>
          )}

          {!result.contested && (
            <p className="text-lg text-gray-200">
              Everyone else folded. <strong>{result.players[0]?.name}</strong> takes the pot; no cards are
              shown.
            </p>
          )}

          <ul className="space-y-2">
            {result.players.map((p) => (
              <li
                key={p.seat}
                className={`rounded-xl border px-4 py-3 ${
                  p.won > 0 ? 'border-green-500 bg-green-950/40' : 'border-gray-700 bg-gray-900/50'
                }`}
              >
                <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                  <div className="min-w-32">
                    <div className="text-lg font-semibold">{p.name}</div>
                    <div className="text-xs text-gray-400">Seat {p.seat}</div>
                  </div>

                  {result.contested && <CardRow cards={p.cards} />}

                  {result.contested && (
                    <div className="min-w-40 flex-1">
                      {p.hands.map((h, i) => (
                        <div key={i} className="flex flex-wrap items-center gap-2 py-0.5">
                          {multiBoard && (
                            <span className="text-xs text-gray-400">Board {i + 1}</span>
                          )}
                          <span className="font-medium">{h.label}</span>
                          <CardRow cards={h.cards} size="sm" />
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="ml-auto flex items-center gap-4 text-right">
                    <div>
                      <div className="text-xs text-gray-400">Stack</div>
                      <div className="text-sm">
                        {money(p.stackBefore)} → <span className="font-semibold">{money(p.stackAfter)}</span>
                      </div>
                    </div>
                    <div className="min-w-24">
                      <span
                        className={`inline-block rounded-md px-2 py-0.5 text-xs font-bold ${RESULT_STYLE[p.result]}`}
                      >
                        {RESULT_LABEL[p.result]}
                      </span>
                      <div
                        className={`text-xl font-bold ${p.won > 0 ? 'text-green-400' : 'text-gray-500'}`}
                      >
                        {p.won > 0 ? signedMoney(p.won) : '$0'}
                      </div>
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>

          <div>
            <h3 className="mb-2 text-sm font-medium uppercase tracking-wide text-gray-400">
              Where the money goes
            </h3>
            <ul className="space-y-2">
              {result.pots.map((pot) => (
                <li key={pot.label} className="rounded-xl bg-gray-900/60 px-4 py-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-semibold">
                      {pot.label} · {money(pot.amount)}
                    </span>
                    {pot.eligible.length > 1 && (
                      <span className="text-xs text-gray-400">
                        Eligible: {pot.eligible.map(name).join(', ')}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-sm text-gray-200">
                    {pot.winners.map((w) => (
                      <span key={w.seat} className="mr-4 inline-block">
                        <strong className="text-green-400">{name(w.seat)}</strong> {money(w.amount)}
                      </span>
                    ))}
                    {multiBoard &&
                      pot.boards.map((b) => (
                        <span key={b.board} className="mr-4 inline-block text-gray-400">
                          Board {b.board + 1}: {b.winners.map(name).join(' & ')} ({b.hand})
                        </span>
                      ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <footer className="border-t border-gray-700 p-4">
          <button
            type="button"
            disabled={disabled}
            onClick={onNextHand}
            className="min-h-16 w-full rounded-xl bg-green-500 text-2xl font-bold text-gray-900 active:bg-green-400 disabled:bg-gray-600 disabled:text-gray-400"
          >
            Next Hand
          </button>
        </footer>
      </section>
    </div>
  )
}
