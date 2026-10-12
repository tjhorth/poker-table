import { useState } from 'react'
import { send } from '../api/socket'
import { money, signedMoney } from '../lib/money'
import type { DealerState } from '../types'

interface Props {
  seat: number
  state: DealerState
  onDone: () => void
}

// Seats a player in an open seat: someone new, or someone who left earlier.
export function SeatPlayerForm({ seat, state, onDone }: Props) {
  const returning = state.inactive
  const [mode, setMode] = useState<'new' | 'returning'>(returning.length > 0 ? 'returning' : 'new')
  const [name, setName] = useState('')
  const [pickedId, setPickedId] = useState<number | null>(returning[0]?.id ?? null)
  const picked = returning.find((p) => p.id === pickedId) ?? null
  const [stack, setStack] = useState(returning[0] ? String(returning[0].stack) : '')

  const stackN = Number(stack) || 0
  const canEdit = state.canEditStacks
  const nameTrim = name.trim()

  const pick = (id: number) => {
    const p = returning.find((r) => r.id === id)
    setPickedId(id)
    if (p) setStack(String(p.stack)) // they come back with what they left with
  }

  const diff = picked ? stackN - picked.stack : 0

  return (
    <div className="space-y-4 overflow-y-auto p-5">
      <div className="grid grid-cols-2 gap-2 rounded-xl bg-gray-900 p-1">
        {(
          [
            ['returning', `Returning player${returning.length ? ` (${returning.length})` : ''}`],
            ['new', 'New player'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            aria-pressed={mode === id}
            disabled={id === 'returning' && returning.length === 0}
            onClick={() => {
              setMode(id)
              setStack(id === 'returning' && picked ? String(picked.stack) : '')
            }}
            className={`min-h-12 rounded-lg font-semibold disabled:text-gray-600 ${
              mode === id ? 'bg-yellow-400 text-gray-900' : 'text-gray-200 active:bg-gray-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === 'returning' ? (
        <ul className="space-y-2">
          {returning.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                aria-pressed={pickedId === p.id}
                onClick={() => pick(p.id)}
                className={`flex w-full items-center justify-between rounded-xl border-2 px-4 py-3 text-left ${
                  pickedId === p.id ? 'border-yellow-300 bg-yellow-400/10' : 'border-gray-700 bg-gray-900'
                }`}
              >
                <span className="text-lg font-semibold">{p.name}</span>
                <span className="text-right text-sm text-gray-300">
                  Left with <strong className="text-white">{money(p.stack)}</strong>
                  <span
                    className={`ml-3 font-semibold ${
                      p.net > 0 ? 'text-green-400' : p.net < 0 ? 'text-red-400' : 'text-gray-400'
                    }`}
                  >
                    Net {p.net === 0 ? '$0' : signedMoney(p.net)}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <label className="block">
          <span className="mb-1 block text-sm text-gray-300">Name</span>
          <input
            value={name}
            maxLength={16}
            onChange={(e) => setName(e.target.value)}
            className="min-h-12 w-full rounded-lg bg-gray-900 px-3 text-xl outline-none"
          />
        </label>
      )}

      <label className="block">
        <span className="mb-1 block text-sm text-gray-300">
          {mode === 'returning' ? 'Stack to sit down with' : 'Buy-in'}
        </span>
        <input
          inputMode="numeric"
          value={stack}
          placeholder="0"
          onChange={(e) => setStack(e.target.value.replace(/[^0-9]/g, ''))}
          className="min-h-12 w-full rounded-lg bg-gray-900 px-3 text-xl outline-none"
        />
      </label>

      {mode === 'returning' && picked && diff !== 0 && stackN > 0 && (
        <p className="text-sm text-gray-300">
          {diff > 0
            ? `${money(diff)} more than they left with: counted as an add-on.`
            : `${money(-diff)} less than they left with: counted as chips taken off the table.`}
        </p>
      )}
      {!canEdit && <p className="text-sm text-yellow-300">Players can be seated between hands.</p>}

      <button
        type="button"
        disabled={!canEdit || stackN <= 0 || (mode === 'new' ? !nameTrim : picked === null)}
        onClick={() => {
          if (mode === 'new') send({ cmd: 'add_player', seat, name: nameTrim, stack: stackN })
          else if (picked) send({ cmd: 'seat_returning', seat, id: picked.id, stack: stackN })
          onDone()
        }}
        className="min-h-14 w-full rounded-xl bg-green-500 text-xl font-bold text-gray-900 active:bg-green-400 disabled:bg-gray-600 disabled:text-gray-400"
      >
        {mode === 'returning' && picked ? `Seat ${picked.name} in seat ${seat}` : `Seat player in seat ${seat}`}
      </button>
    </div>
  )
}
