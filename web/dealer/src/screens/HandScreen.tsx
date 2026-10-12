import { useEffect, useState } from 'react'
import { send } from '../api/socket'
import { ShowdownModal } from '../components/ShowdownModal'
import { TableView } from '../components/TableView'
import { money } from '../lib/money'
import { useTable } from '../state/store'
import type { DealerState } from '../types'

function statusLine(s: DealerState): { title: string; detail: string } {
  const name = (seat: number | null) => s.players.find((p) => p.seat === seat)?.name ?? ''
  const seated = s.players.filter((p) => p.name).length
  const registered = s.players.filter((p) => p.cards > 0).length
  switch (s.phase) {
    case 'waiting':
      return s.canDeal
        ? { title: 'Ready to deal', detail: `${seated} players seated. Press Deal Hand to start.` }
        : { title: 'Waiting', detail: s.note ?? 'Waiting for players…' }
    case 'dealing':
      return { title: 'Dealing', detail: `Hole cards registered: ${registered} of ${seated}` }
    case 'blinds':
      return {
        title: 'Posting blinds',
        detail: s.config.bomb ? 'Waiting for every ante' : 'Waiting for the blinds',
      }
    case 'betting':
      return s.toAct
        ? { title: `On action: ${name(s.toAct)}`, detail: 'Betting in progress' }
        : { title: 'Betting', detail: 'Waiting for the next action' }
    case 'awaiting_board':
      return {
        title: `Waiting for the ${s.awaiting.street ?? 'next street'}`,
        detail: 'Betting is complete. Deal the next card(s).',
      }
    case 'showdown_ready':
      return s.uncontested
        ? { title: 'Everyone folded', detail: 'Award the pot to finish the hand' }
        : { title: 'Betting complete', detail: 'Ready for showdown' }
    case 'showdown':
      return { title: 'Result shown', detail: 'Press Next Hand to start the next hand' }
  }
}

export function HandScreen({ state }: { state: DealerState }) {
  const connected = useTable((s) => s.connected)
  const [busy, setBusy] = useState(false)
  const [hidden, setHidden] = useState(false)

  // A new phase or hand means the server acted on whatever was pressed.
  useEffect(() => {
    setBusy(false)
    setHidden(false)
  }, [state.phase, state.hand])

  const line = statusLine(state)
  const name = (seat: number) => state.players.find((p) => p.seat === seat)?.name ?? `Seat ${seat}`
  const potTotal = state.pots.reduce((sum, p) => sum + p.amount, 0)
  const showModal = state.phase === 'showdown' && state.showdown && !hidden

  const press = (cmd: 'deal_hand' | 'showdown' | 'next_hand') => {
    if (send({ cmd })) setBusy(true)
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col gap-3 p-3 lg:flex-row">
      <div className="flex min-h-0 flex-1 items-center justify-center">
        <TableView
          players={state.players}
          toAct={state.phase === 'betting' ? state.toAct : null}
          boards={state.boards}
          potTotal={potTotal}
        />
      </div>

      <aside className="flex shrink-0 flex-col gap-3 text-white lg:w-80">
        <section className="rounded-xl bg-gray-800 p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-gray-400">Status</div>
          <div className="text-xl font-semibold">{line.title}</div>
          <div className="text-sm text-gray-300">{line.detail}</div>
        </section>

        <section className="rounded-xl bg-gray-800 p-4">
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400">
            {state.pots.length > 1 ? 'Pots' : 'Pot'}
          </div>
          <ul className="space-y-1.5">
            {state.pots.map((pot, i) => (
              <li key={i}>
                <div className="flex items-baseline justify-between">
                  <span className="text-sm text-gray-200">
                    {state.pots.length === 1 ? 'Pot' : i === 0 ? 'Main pot' : `Side pot ${i}`}
                  </span>
                  <span className="text-xl font-semibold">{money(pot.amount)}</span>
                </div>
                {state.pots.length > 1 && pot.eligible.length > 0 && (
                  <div className="text-xs text-gray-400">
                    Eligible: {pot.eligible.map(name).join(', ')}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>

        <div className="mt-auto flex flex-col gap-3">
          {state.phase === 'waiting' && (
            <button
              type="button"
              disabled={!state.canDeal || busy || !connected}
              onClick={() => press('deal_hand')}
              className="min-h-16 rounded-xl bg-green-500 text-2xl font-bold text-gray-900 active:bg-green-400 disabled:bg-gray-600 disabled:text-gray-400"
            >
              Deal Hand
            </button>
          )}
          <button
            type="button"
            disabled={!state.canShowdown || busy || !connected}
            onClick={() => press('showdown')}
            className="min-h-16 rounded-xl bg-yellow-400 text-2xl font-bold text-gray-900 active:bg-yellow-300 disabled:bg-gray-600 disabled:text-gray-400"
          >
            {state.uncontested ? 'Award Pot' : 'Showdown'}
          </button>
          <button
            type="button"
            disabled={!state.canNextHand || busy || !connected}
            onClick={() => press('next_hand')}
            className="min-h-16 rounded-xl bg-green-500 text-2xl font-bold text-gray-900 active:bg-green-400 disabled:bg-gray-600 disabled:text-gray-400"
          >
            Next Hand
          </button>
          {state.phase === 'showdown' && hidden && (
            <button
              type="button"
              onClick={() => setHidden(false)}
              className="min-h-12 rounded-xl bg-gray-700 text-lg font-medium text-white active:bg-gray-600"
            >
              Show result
            </button>
          )}
        </div>
      </aside>

      {showModal && (
        <ShowdownModal
          state={state}
          disabled={busy || !connected}
          onNextHand={() => press('next_hand')}
          onHide={() => setHidden(true)}
        />
      )}
    </div>
  )
}
