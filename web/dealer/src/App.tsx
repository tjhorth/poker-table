import { SeatsScreen } from './screens/SeatsScreen'

export default function App() {
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-gray-700">
      <header className="flex shrink-0 flex-nowrap gap-x-6 gap-y-1 p-3">
        <p className="text-red-600 font-bold">Offline</p>
        <p className="text-white font-bold">Hand #</p>
        <p className="text-white font-bold">Game Style</p>
        <p className="text-green-500 font-bold">No pending changes</p>
      </header>

      <main className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:flex-row">
        <SeatsScreen />
        <aside className="flex shrink-0 flex-col gap-2 lg:w-72">
          <p className="text-white">Action</p>
          <p className="text-white">Pot</p>
          <p className="text-white">Street</p>
          <button className="text-white">Next Hand</button>
        </aside>
      </main>

      <nav className="flex shrink-0 max-w-full">
        <button className="min-h-14 flex-1 text-yellow-300">Hand</button>
        <button className="min-h-14 flex-1 text-yellow-300">Seats</button>
        <button className="min-h-14 flex-1 text-yellow-300">Setup (PIN)</button>
        <button className="min-h-14 flex-1 text-yellow-300">Stream</button>
      </nav>
    </div>
  )
}
