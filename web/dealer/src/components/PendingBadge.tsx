import type { DealerState } from '../types'

export function PendingBadge({ pending }: { pending: DealerState['pending'] }) {
  if (!pending) {
    return <span className="text-sm font-semibold text-green-400">No pending changes</span>
  }
  return (
    <span className="rounded-md bg-yellow-400 px-2 py-1 text-sm font-semibold text-gray-900">
      Pending: {pending.label} · Blinds {pending.blinds} — applies next hand
    </span>
  )
}
