import type { GameSummary } from '../types'

// Saved game summaries live on the engine; this reads the most recent ones.
function api(path: string, extra = ''): string {
  const params = new URLSearchParams(location.search)
  const server = params.get('server')
  const token = params.get('token')
  const origin = server ? `${location.protocol}//${server}` : ''
  const query = [extra, token ? `token=${encodeURIComponent(token)}` : ''].filter(Boolean).join('&')
  return `${origin}${path}${query ? `?${query}` : ''}`
}

export async function fetchRecentGames(limit = 3): Promise<GameSummary[]> {
  const res = await fetch(api('/api/games', `limit=${limit}`))
  if (!res.ok) throw new Error(`The table returned ${res.status}`)
  return (await res.json()) as GameSummary[]
}

export function gameCsvUrl(id: string): string {
  return api(`/api/games/${id}.csv`)
}
