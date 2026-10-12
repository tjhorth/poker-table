import { useTable } from '../state/store'
import type { Command, DealerState } from '../types'

let ws: WebSocket | null = null
let retry = 500
let timer: number | undefined
let errorTimer: number | undefined

function endpoint(): string {
  // ?server=host:8000 talks to the engine directly; otherwise go through the
  // page's own origin (Vite proxies /ws to the API in development).
  const server = new URLSearchParams(location.search).get('server')
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const token = new URLSearchParams(location.search).get('token')
  return `${proto}://${server ?? location.host}/ws/dealer${token ? `?token=${encodeURIComponent(token)}` : ''}`
}

export function connect(): void {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  window.clearTimeout(timer)

  const socket = new WebSocket(endpoint())
  ws = socket

  socket.onopen = () => {
    retry = 500
    useTable.getState().setConnected(true)
  }

  socket.onmessage = (event) => {
    const msg = JSON.parse(event.data) as
      | { type: 'state'; state: DealerState }
      | { type: 'error'; message: string }
    if (msg.type === 'state') {
      useTable.getState().setState(msg.state)
    } else if (msg.type === 'error') {
      useTable.getState().setError(msg.message)
      window.clearTimeout(errorTimer)
      errorTimer = window.setTimeout(() => useTable.getState().setError(null), 4000)
    }
  }

  socket.onclose = () => {
    if (ws === socket) ws = null
    useTable.getState().setConnected(false)
    timer = window.setTimeout(connect, retry)
    retry = Math.min(retry * 2, 5000)
  }

  socket.onerror = () => socket.close()
}

export function send(command: Command): boolean {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    useTable.getState().setError('Not connected to the table. Reconnecting…')
    return false
  }
  ws.send(JSON.stringify(command))
  return true
}
