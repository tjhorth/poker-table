import type { GameSummary } from '../types'

// Saved game summaries live on the engine; this reads the most recent ones.
export async function fetchRecentGames(limit = 3): Promise<GameSummary[]> {
  const base = new URLSearchParams(location.search).get('server')
  const origin = base ? `${location.protocol}//${base}` : ''
  const res = await fetch(`${origin}/api/games?limit=${limit}`)
  if (!res.ok) throw new Error(`The table returned ${res.status}`)
  return (await res.json()) as GameSummary[]
}

export function gameCsvUrl(id: string): string {
  const base = new URLSearchParams(location.search).get('server')
  const origin = base ? `${location.protocol}//${base}` : ''
  return `${origin}/api/games/${id}.csv`
}
