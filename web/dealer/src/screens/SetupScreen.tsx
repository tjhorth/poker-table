import { useState } from 'react'
import { send } from '../api/socket'
import { NumberField } from '../components/NumberField'
import { PastGamesModal } from '../components/PastGamesModal'
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
  const [confirmNew, setConfirmNew] = useState(false)
  const [showPast, setShowPast] = useState(false)

  if (!unlocked) return <PinGate onUnlock={() => setUnlocked(true)} />

  const set = (changes: Partial<GameConfig>) => setDraft((d) => ({ ...d, ...changes }))
  const matchesCurrent = sameConfig(draft, state.config)
  const matchesPending = state.pending ? sameConfig(draft, state.pending.config) : matchesCurrent
  const blindsLabel = `${draft.sb}/${draft.bb}`
  const participants = state.players.filter((p) => p.name !== null).length + state.inactive.length
  const handsInGame = state.game.handsPlayed + (state.phase === 'showdown' ? 1 : 0)
  const nextConfig = state.pending?.config ?? state.config
  const validBlinds = draft.sb >= 1 && draft.bb >= draft.sb

  return (
    <div className="relative flex min-h-0 flex-1 flex-col text-white">
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-gray-300">
            Playing now: <strong className="text-white">{state.gameLabel}</strong> · Blinds{' '}
            <strong className="text-white">{state.blinds}</strong>
            {state.config.bomb && <> · Ante <strong className="text-white">${state.config.ante}</strong></>}
          </p>
          <button
            type="button"
            onClick={() => setShowPast(true)}
            className="min-h-12 rounded-xl bg-sky-500 px-5 text-lg font-bold text-gray-900 active:bg-sky-400"
          >
            Past games
          </button>
        </div>

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

        <section className="mt-4 rounded-2xl border border-red-500/40 bg-gray-800 p-4">
          <h2 className="text-lg font-semibold">New game</h2>
          <p className="mb-3 text-sm text-gray-400">
            Saves a summary of this game, clears every seat, and keeps the settings selected above
            ({state.pending ? state.pending.label : state.gameLabel}).
          </p>
          <button
            type="button"
            disabled={!state.canEditStacks || participants === 0}
            onClick={() => setConfirmNew(true)}
            className="min-h-14 rounded-xl border-2 border-red-500 px-6 text-lg font-semibold text-red-400 active:bg-red-500/20 disabled:border-gray-600 disabled:text-gray-500"
          >
            Start a new game…
          </button>
          {!state.canEditStacks ? (
            <p className="mt-2 text-sm text-yellow-300">
              Available between hands, after the showdown result.
            </p>
          ) : participants === 0 ? (
            <p className="mt-2 text-sm text-gray-400">Nobody has played yet, so there is nothing to save.</p>
          ) : null}

          {state.lastSummary && (
            <p className="mt-4 rounded-lg bg-gray-900 p-3 text-sm text-gray-300">
              Last game saved: {state.lastSummary.players} player
              {state.lastSummary.players === 1 ? '' : 's'}, {state.lastSummary.handsPlayed} hand
              {state.lastSummary.handsPlayed === 1 ? '' : 's'}
              <span className="mt-1 block break-all text-xs text-gray-500">{state.lastSummary.file}</span>
            </p>
          )}
        </section>
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

      {showPast && <PastGamesModal onClose={() => setShowPast(false)} />}

      {confirmNew && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/70 p-4">
          <section
            role="dialog"
            aria-modal="true"
            aria-label="Start a new game"
            className="w-full max-w-lg rounded-2xl bg-gray-800 p-6 shadow-2xl"
          >
            <h2 className="text-2xl font-bold">Start a new game?</h2>
            <ul className="my-4 list-disc space-y-2 pl-5 text-gray-200">
              <li>
                A summary of this game is saved: <strong>{participants}</strong> player
                {participants === 1 ? '' : 's'}, <strong>{handsInGame}</strong> hand
                {handsInGame === 1 ? '' : 's'}, with each player's hands played, buy-ins, ending
                stack, and net.
              </li>
              <li>Every seat is cleared, and so is the list of players who left.</li>
              <li>
                The hand count restarts and the settings stay:{' '}
                <strong>
                  {gameLabel(nextConfig)} · Blinds {nextConfig.sb}/{nextConfig.bb}
                  {nextConfig.bomb && ` · Ante $${nextConfig.ante}`}
                </strong>
                .
              </li>
            </ul>
            <p className="mb-5 text-sm text-gray-400">
              Seat players again from the Seats tab, then press Deal Hand on the Hand tab.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setConfirmNew(false)}
                className="min-h-14 rounded-xl bg-gray-700 text-lg font-medium active:bg-gray-600"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  send({ cmd: 'new_game' })
                  setConfirmNew(false)
                }}
                className="min-h-14 rounded-xl bg-red-500 text-lg font-bold text-white active:bg-red-400"
              >
                Start new game
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
