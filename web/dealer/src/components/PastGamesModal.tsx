import { useEffect, useState } from 'react'
import { fetchRecentGames, gameCsvUrl } from '../api/games'
import { money, signedMoney } from '../lib/money'
import type { GameSummary } from '../types'

function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function Net({ value }: { value: number }) {
  const tone = value > 0 ? 'text-green-400' : value < 0 ? 'text-red-400' : 'text-gray-400'
  return <span className={`font-semibold ${tone}`}>{value === 0 ? '$0' : signedMoney(value)}</span>
}

function GameCard({ game }: { game: GameSummary }) {
  const anteText = game.game.bombPot && game.game.ante ? ` · Ante $${game.game.ante}` : ''
  return (
    <article className="rounded-xl bg-gray-900 p-4">
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <h3 className="text-lg font-semibold">
            {game.game.label} · Blinds {game.game.blinds}
            {anteText}
          </h3>
          <p className="text-sm text-gray-400">
            {when(game.startedAt)} – {when(game.endedAt)} · {game.players.length} player
            {game.players.length === 1 ? '' : 's'} · {game.handsPlayed} hand
            {game.handsPlayed === 1 ? '' : 's'}
          </p>
        </div>
        <a
          href={gameCsvUrl(game.id)}
          download
          className="rounded-lg bg-gray-700 px-3 py-2 text-sm font-medium active:bg-gray-600"
        >
          Download CSV
        </a>
      </header>

      <table className="w-full text-left">
        <thead className="text-xs uppercase tracking-wide text-gray-400">
          <tr>
            <th className="py-1 pr-3">Player</th>
            <th className="px-3 py-1 text-right">Hands</th>
            <th className="px-3 py-1 text-right">Bought in</th>
            <th className="px-3 py-1 text-right">Ending stack</th>
            <th className="py-1 pl-3 text-right">Net</th>
          </tr>
        </thead>
        <tbody>
          {game.players.map((p) => (
            <tr key={p.name} className="border-t border-gray-800">
              <td className="py-2 pr-3 font-medium">
                {p.name}
                {p.status === 'left' && <span className="ml-2 text-xs text-gray-500">left early</span>}
              </td>
              <td className="px-3 py-2 text-right text-gray-300">{p.handsPlayed}</td>
              <td className="px-3 py-2 text-right">{money(p.buyIn)}</td>
              <td className="px-3 py-2 text-right text-green-400">{money(p.endingStack)}</td>
              <td className="py-2 pl-3 text-right">
                <Net value={p.net} />
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-gray-600 text-sm text-gray-300">
            <td className="py-2 pr-3">Total</td>
            <td />
            <td className="px-3 py-2 text-right">{money(game.totals.buyIn)}</td>
            <td className="px-3 py-2 text-right">{money(game.totals.endingStack)}</td>
            <td className="py-2 pl-3 text-right">
              <Net value={game.totals.net} />
            </td>
          </tr>
        </tfoot>
      </table>
    </article>
  )
}

export function PastGamesModal({ onClose }: { onClose: () => void }) {
  const [games, setGames] = useState<GameSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetchRecentGames(3)
      .then((g) => alive && setGames(g))
      .catch((e: Error) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/70 p-3">
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Past games"
        className="flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-gray-800 text-white shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-gray-700 px-5 py-4">
          <h2 className="text-2xl font-bold">Past games</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-gray-700 px-4 py-2 font-medium active:bg-gray-600"
          >
            Close
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          {error && <p className="text-red-400">Couldn't load past games: {error}</p>}
          {!error && games === null && <p className="text-gray-300">Loading…</p>}
          {games && games.length === 0 && (
            <p className="text-gray-300">
              No saved games yet. Starting a new game saves a summary of the one before it.
            </p>
          )}
          {games && games.length > 0 && (
            <p className="text-sm text-gray-400">
              The {games.length === 1 ? 'only saved game' : `last ${games.length} games`}, newest first.
            </p>
          )}
          {games?.map((g) => <GameCard key={g.id} game={g} />)}
        </div>
      </section>
    </div>
  )
}
