import { useState } from 'react'
import { send } from '../api/socket'
import { NumberField } from '../components/NumberField'
import { PinGate } from '../components/PinGate'
import { gameLabel, sameConfig } from '../lib/game'
import type { DealerState, GameConfig } from '../types'

function Choice({
  selected,
  onClick,
  children,
}: {
  selected: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`min-h-14 flex-1 rounded-xl px-4 text-lg font-semibold ${
        selected ? 'bg-yellow-400 text-gray-900' : 'bg-gray-700 text-white active:bg-gray-600'
      }`}
    >
      {children}
    </button>
  )
}

function Panel({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl bg-gray-800 p-4">
      <h2 className="text-lg font-semibold">{title}</h2>
      {hint && <p className="mb-3 text-sm text-gray-400">{hint}</p>}
      <div className={hint ? '' : 'mt-3'}>{children}</div>
    </section>
  )
}

export function SetupScreen({ state }: { state: DealerState }) {
  const [unlocked, setUnlocked] = useState(false)
  const [draft, setDraft] = useState<GameConfig>(state.pending?.config ?? state.config)

  if (!unlocked) return <PinGate onUnlock={() => setUnlocked(true)} />

  const set = (changes: Partial<GameConfig>) => setDraft((d) => ({ ...d, ...changes }))
  const matchesCurrent = sameConfig(draft, state.config)
  const matchesPending = state.pending ? sameConfig(draft, state.pending.config) : matchesCurrent
  const blindsLabel = `${draft.sb}/${draft.bb}`
  const validBlinds = draft.sb >= 1 && draft.bb >= draft.sb

  return (
    <div className="flex min-h-0 flex-1 flex-col text-white">
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <p className="mb-4 text-gray-300">
          Playing now: <strong className="text-white">{state.gameLabel}</strong> · Blinds{' '}
          <strong className="text-white">{state.blinds}</strong>
          {state.config.bomb && <> · Ante <strong className="text-white">${state.config.ante}</strong></>}
        </p>

        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Game">
            <div className="flex gap-3">
              {Object.entries(state.options.variants).map(([key, label]) => (
                <Choice
                  key={key}
                  selected={draft.variant === key}
                  onClick={() => set({ variant: key as GameConfig['variant'] })}
                >
                  {label}
                </Choice>
              ))}
            </div>
          </Panel>

          <Panel title="Boards">
            <div className="flex gap-3">
              <Choice selected={draft.boards === 1} onClick={() => set({ boards: 1 })}>
                Single board
              </Choice>
              <Choice selected={draft.boards === 2} onClick={() => set({ boards: 2 })}>
                Double board
              </Choice>
            </div>
          </Panel>

          <Panel
            title="Bomb pots"
            hint="Every hand: everyone antes, there is no preflop betting, and the flop comes straight away."
          >
            <div className="flex gap-3">
              <Choice selected={!draft.bomb} onClick={() => set({ bomb: false })}>
                Off
              </Choice>
              <Choice selected={draft.bomb} onClick={() => set({ bomb: true })}>
                On
              </Choice>
            </div>
            {draft.bomb && (
              <div className="mt-4">
                <NumberField
                  label="Ante (every player)"
                  value={draft.ante}
                  min={1}
                  step={Math.max(1, draft.bb)}
                  onChange={(ante) => set({ ante })}
                />
              </div>
            )}
          </Panel>

          <Panel title="Blinds">
            <div className="mb-4 flex flex-wrap gap-2">
              {state.options.blindPresets.map((preset) => {
                const [sb, bb] = preset.split('/').map(Number)
                return (
                  <Choice
                    key={preset}
                    selected={draft.sb === sb && draft.bb === bb}
                    onClick={() => set({ sb, bb })}
                  >
                    {preset}
                  </Choice>
                )
              })}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <NumberField
                label="Small blind"
                value={draft.sb}
                min={1}
                step={Math.max(1, Math.round(draft.sb / 2))}
                onChange={(sb) => set({ sb })}
              />
              <NumberField
                label="Big blind"
                value={draft.bb}
                min={1}
                step={Math.max(1, Math.round(draft.bb / 2))}
                onChange={(bb) => set({ bb })}
              />
            </div>
            {!validBlinds && (
              <p className="mt-2 text-sm text-red-400">The big blind must be at least the small blind.</p>
            )}
          </Panel>
        </div>
      </div>

      <footer className="flex shrink-0 flex-wrap items-center gap-3 border-t border-gray-700 bg-gray-800 p-3">
        <div className="min-w-0 flex-1">
          <div className="text-xs uppercase tracking-wide text-gray-400">Next hand will be</div>
          <div className="truncate text-lg font-semibold">
            {gameLabel(draft)} · Blinds {blindsLabel}
            {draft.bomb && ` · Ante $${draft.ante}`}
          </div>
          <div className="text-xs text-gray-400">Changes never affect the hand in progress.</div>
        </div>
        {(state.pending || !matchesCurrent) && (
          <button
            type="button"
            onClick={() => {
              setDraft(state.config)
              if (state.pending) send({ cmd: 'set_config', config: state.config })
            }}
            className="min-h-14 rounded-xl bg-gray-700 px-5 text-lg font-medium active:bg-gray-600"
          >
            {state.pending ? 'Cancel pending change' : 'Reset'}
          </button>
        )}
        <button
          type="button"
          disabled={matchesPending || !validBlinds}
          onClick={() => send({ cmd: 'set_config', config: draft })}
          className="min-h-14 rounded-xl bg-green-500 px-6 text-lg font-bold text-gray-900 active:bg-green-400 disabled:bg-gray-600 disabled:text-gray-400"
        >
          Apply at next hand
        </button>
      </footer>
    </div>
  )
}
