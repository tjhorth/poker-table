import { create } from 'zustand'
import type { DealerState } from '../types'

interface TableStore {
  state: DealerState | null
  connected: boolean
  error: string | null
  setState: (s: DealerState) => void
  setConnected: (c: boolean) => void
  setError: (e: string | null) => void
}

// The server is the source of truth: this just holds the latest snapshot.
export const useTable = create<TableStore>((set) => ({
  state: null,
  connected: false,
  error: null,
  setState: (state) => set({ state }),
  setConnected: (connected) => set({ connected }),
  setError: (error) => set({ error }),
}))
