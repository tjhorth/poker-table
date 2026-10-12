import { useState } from 'react'
import { send } from '../api/socket'
import { money, signedMoney } from '../lib/money'
import type { DealerState, PlayerState } from '../types'
import { SeatPlayerForm } from './SeatPlayerForm'

interface Props {
  player: PlayerState
  state: DealerState
  onClose: () => void
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl bg-gray-900 px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-gray-400">{label}</div>
      <div className={`text-xl font-bold ${tone ?? ''}`}>{value}</div>
    </div>
  )
}

export function SeatSheet({ player, state, onClose }: Props) {
  const empty = player.name === null
  const [name, setName] = useState(player.name ?? '')
  const [amount, setAmount] = useState('')
  const [confirmRemove, setConfirmRemove] = useState(false)

  const amountN = Number(amount) || 0
  const canEdit = state.canEditStacks
  const netTone = player.net > 0 ? 'text-green-400' : player.net < 0 ? 'text-red-400' : 'text-gray-300'
  const nameTrim = name.trim()

  const shell = (children: React.ReactNode) => (
    <div className="absolute inset-0 z-20 flex items-end justify-center bg-black/70 p-3 lg:items-center">
      <section
        role="dialog"
        aria-modal="true"
        aria-label={`Seat ${player.seat}`}
        className="flex max-h-full w-full max-w-xl flex-col overflow-hidden rounded-2xl bg-gray-800 text-white shadow-2xl"
      >
        {children}
      </section>
    </div>
  )

  const header = (
    <header className="flex items-center justify-between border-b border-gray-700 px-5 py-4">
      <h2 className="text-2xl font-bold">
        Seat {player.seat}
        {!empty && <span className="text-gray-300"> · {player.name}</span>}
      </h2>
      <button
        type="button"
        onClick={onClose}
        className="rounded-lg bg-gray-700 px-4 py-2 font-medium active:bg-gray-600"
      >
        Close
      </button>
    </header>
  )

  if (empty) {
    return shell(
      <>
        {header}
        <SeatPlayerForm seat={player.seat} state={state} onDone={onClose} />
      </>,
    )
  }

  return shell(
    <>
      {header}
      <div className="space-y-5 overflow-y-auto p-5">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Stack" value={money(player.stack)} tone="text-green-400" />
          <Stat label="Bought in" value={money(player.buyIn)} />
          <Stat label="Cashed out" value={money(player.cashedOut)} />
          <Stat
            label="Net"
            value={player.net === 0 ? '$0' : signedMoney(player.net)}
            tone={netTone}
          />
        </div>

        <div>
          <label className="mb-1 block text-sm text-gray-300" htmlFor="seat-name">
            Name
          </label>
          <div className="flex gap-2">
            <input
              id="seat-name"
              value={name}
              maxLength={16}
              onChange={(e) => setName(e.target.value)}
              className="min-h-12 min-w-0 flex-1 rounded-lg bg-gray-900 px-3 text-xl outline-none"
            />
            <button
              type="button"
              disabled={!nameTrim || nameTrim === player.name}
              onClick={() => send({ cmd: 'edit_name', seat: player.seat, name: nameTrim })}
              className="rounded-lg bg-sky-500 px-5 text-lg font-bold text-gray-900 active:bg-sky-400 disabled:bg-gray-600 disabled:text-gray-400"
            >
              Save
            </button>
          </div>
        </div>

        <div>
          <label className="mb-1 block text-sm text-gray-300" htmlFor="seat-amount">
            Chips
          </label>
          <input
            id="seat-amount"
            inputMode="numeric"
            value={amount}
            placeholder="Amount"
            onChange={(e) => setAmount(e.target.value.replace(/[^0-9]/g, ''))}
            className="mb-3 min-h-12 w-full rounded-lg bg-gray-900 px-3 text-xl outline-none"
          />
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              disabled={!canEdit || amountN <= 0}
              onClick={() => {
                send({ cmd: 'adjust_stack', seat: player.seat, amount: amountN })
                setAmount('')
              }}
              className="min-h-14 rounded-xl bg-green-500 text-lg font-bold text-gray-900 active:bg-green-400 disabled:bg-gray-600 disabled:text-gray-400"
            >
              Add to stack
            </button>
            <button
              type="button"
              disabled={!canEdit || amountN <= 0 || amountN > player.stack}
              onClick={() => {
                send({ cmd: 'adjust_stack', seat: player.seat, amount: -amountN })
                setAmount('')
              }}
              className="min-h-14 rounded-xl bg-orange-400 text-lg font-bold text-gray-900 active:bg-orange-300 disabled:bg-gray-600 disabled:text-gray-400"
            >
              Subtract from stack
            </button>
          </div>
          <p className="mt-2 text-sm text-gray-400">
            Adding counts as a buy-in. Subtracting counts as cashing chips out.
            {!canEdit && (
              <span className="mt-1 block text-yellow-300">
                Stack changes are available between hands, after the showdown result.
              </span>
            )}
          </p>
        </div>

        <div className="border-t border-gray-700 pt-4">
          {!confirmRemove ? (
            <button
              type="button"
              disabled={!canEdit}
              onClick={() => setConfirmRemove(true)}
              className="min-h-12 w-full rounded-xl border-2 border-red-500 text-lg font-semibold text-red-400 active:bg-red-500/20 disabled:border-gray-600 disabled:text-gray-500"
            >
              Remove player
            </button>
          ) : (
            <div className="rounded-xl bg-red-950/60 p-4">
              <p className="mb-3">
                Remove <strong>{player.name}</strong> from the table? They leave with{' '}
                {money(player.stack)}
                {player.net !== 0 && <> (net {signedMoney(player.net)})</>}
                {' '}and stay on the list, so you can seat them again later.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setConfirmRemove(false)}
                  className="min-h-12 rounded-xl bg-gray-700 text-lg font-medium active:bg-gray-600"
                >
                  Keep player
                </button>
                <button
                  type="button"
                  onClick={() => {
                    send({ cmd: 'remove_player', seat: player.seat })
                    onClose()
                  }}
                  className="min-h-12 rounded-xl bg-red-500 text-lg font-bold text-white active:bg-red-400"
                >
                  Remove
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>,
  )
}
