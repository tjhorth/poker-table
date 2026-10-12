import { useEffect, useState } from 'react'
import { connect } from './api/socket'
import { ConnectionBanner } from './components/ConnectionBanner'
import { PendingBadge } from './components/PendingBadge'
import { useVisibilityResync } from './hooks/useVisibilityResync'
import { capitalize } from './lib/money'
import { HandScreen } from './screens/HandScreen'
import { SeatsScreen } from './screens/SeatsScreen'
import { SetupScreen } from './screens/SetupScreen'
import { useTable } from './state/store'

type Tab = 'hand' | 'seats' | 'setup'
const TABS: { id: Tab; label: string }[] = [
  { id: 'hand', label: 'Hand' },
  { id: 'seats', label: 'Seats' },
  { id: 'setup', label: 'Configs' },
]

export default function App() {
  const state = useTable((s) => s.state)
  const connected = useTable((s) => s.connected)
  const error = useTable((s) => s.error)
  const [tab, setTab] = useState<Tab>('hand')

  useEffect(() => {
    connect()
  }, [])
  useVisibilityResync()

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-gray-900">
      <header className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-1 bg-gray-800 px-4 py-3 text-white">
        <span className="flex items-center gap-2 text-sm font-semibold">
          <span
            className={`h-2.5 w-2.5 rounded-full ${connected ? 'bg-green-400' : 'bg-red-500'}`}
            aria-hidden="true"
          />
          {connected ? 'Live' : 'Offline'}
        </span>
        {state && (
          <span className="text-lg font-semibold">
            {state.gameLabel} · Blinds {state.blinds} · Hand #{state.hand} · {capitalize(state.street)}
          </span>
        )}
        <span className="ml-auto">{state && <PendingBadge pending={state.pending} />}</span>
      </header>

      <ConnectionBanner connected={connected} error={error} />

      {state ? (
        <main className="flex min-h-0 flex-1 flex-col">
          {tab === 'hand' && <HandScreen state={state} />}
          {tab === 'seats' && <SeatsScreen state={state} />}
          {tab === 'setup' && <SetupScreen state={state} />}
        </main>
      ) : (
        <main className="flex flex-1 items-center justify-center text-xl text-gray-300">
          Connecting to the table…
        </main>
      )}

      <nav className="flex shrink-0 bg-gray-800">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            aria-current={tab === t.id ? 'page' : undefined}
            className={`min-h-16 flex-1 text-lg font-semibold ${
              tab === t.id ? 'border-t-4 border-yellow-300 text-yellow-300' : 'border-t-4 border-transparent text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>
    </div>
  )
}
