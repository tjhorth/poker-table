// Shapes sent by the game engine over /ws/dealer.

export type Phase = 'waiting' | 'dealing' | 'betting' | 'showdown_ready' | 'showdown'
export type PlayerStatus = 'active' | 'folded' | 'all_in' | 'empty'

export interface PlayerState {
  seat: number
  name: string | null
  stack: number
  status: PlayerStatus
  bet: number                // chips in front of the player this street
  lastAction: string | null  // "RAISE $6", "FOLD", ...
  cards: number              // how many hole cards are registered (never the cards)
  isButton: boolean
  buyIn: number              // total bought in (first stack plus every add)
  cashedOut: number          // chips taken off the table
  net: number                // stack + cashed out - bought in
}

// A player who has left the table. Their ledger is kept, with no seat.
export interface InactivePlayer {
  id: number
  name: string
  stack: number              // the stack they left with
  buyIn: number
  cashedOut: number
  net: number
}

export interface GameConfig {
  variant: 'nlh' | 'plo4'
  boards: 1 | 2
  bomb: boolean              // every hand is a bomb pot
  ante: number               // bomb pot ante
  sb: number
  bb: number
}

export interface Pot {
  amount: number
  eligible: number[]
}

export interface HandRank {
  label: string              // "Two pair"
  cards: string[]            // the five cards that make it
}

export interface ShowdownPlayer {
  seat: number
  name: string
  cards: string[]            // hole cards, only sent at showdown
  hands: HandRank[]          // one per board
  won: number
  stackBefore: number
  stackAfter: number
  result: 'win' | 'split' | 'lose'
}

export interface ShowdownPot {
  label: string              // "Main Pot", "Side Pot 1", "Pot"
  amount: number
  eligible: number[]
  winners: { seat: number; amount: number }[]
  boards: { board: number; winners: number[]; hand: string }[]
}

export interface ShowdownResult {
  contested: boolean         // false when everyone else folded
  boards: string[][]
  players: ShowdownPlayer[]
  pots: ShowdownPot[]
}

export interface DealerState {
  version: number
  hand: number
  gameLabel: string
  config: GameConfig
  blinds: string
  button: number
  street: string
  phase: Phase
  toAct: number | null
  order: number[]
  players: PlayerState[]
  pots: Pot[]
  boards: string[][]
  holeCards: number
  pending: { config: GameConfig; label: string; blinds: string } | null
  options: { variants: Record<string, string>; blindPresets: string[] }
  inactive: InactivePlayer[]
  canShowdown: boolean
  canEditStacks: boolean
  note: string | null
  canNextHand: boolean
  uncontested: boolean
  showdown: ShowdownResult | null
}

export type Command =
  | { cmd: 'showdown' }
  | { cmd: 'next_hand' }
  | { cmd: 'set_config'; config: Partial<GameConfig> }
  | { cmd: 'edit_name'; seat: number; name: string }
  | { cmd: 'adjust_stack'; seat: number; amount: number }
  | { cmd: 'remove_player'; seat: number }
  | { cmd: 'add_player'; seat: number; name: string; stack: number }
  | { cmd: 'seat_returning'; seat: number; id: number; stack: number }
