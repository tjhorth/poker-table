export function ConnectionBanner({ connected, error }: { connected: boolean; error: string | null }) {
  if (connected && !error) return null
  return (
    <div
      role="status"
      className={`shrink-0 px-4 py-2 text-center text-sm font-semibold ${
        connected ? 'bg-yellow-400 text-gray-900' : 'bg-red-600 text-white'
      }`}
    >
      {connected ? error : 'Connection to the table lost. Showing the last known state; reconnecting…'}
    </div>
  )
}
