import { TableView, type SeatInfo } from '../components/TableView'

const SEAT_COUNT = 8

// Placeholder until seat data comes from the server.
const PLAYERS: Record<number, string> = {
  3: 'Tim H',
}

const SEATS: SeatInfo[] = Array.from({ length: SEAT_COUNT }, (_, i) => ({
  seat: i + 1,
  player: PLAYERS[i + 1] ?? null,
}))

export function SeatsScreen() {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center">
      <TableView seats={SEATS} />
    </div>
  )
}
