import type { GameConfig } from '../types'

// Mirrors the label the engine builds, so the dashboard can preview a draft.
export function gameLabel(cfg: GameConfig): string {
  if (!cfg.bomb && cfg.boards === 1) return cfg.variant === 'nlh' ? 'NLH' : 'PLO 4-card'
  const base = cfg.variant === 'nlh' ? 'NLH' : 'PLO'
  const parts: string[] = []
  if (cfg.bomb) parts.push('Bomb Pot -')
  if (cfg.boards === 2) parts.push('2brd')
  return [...parts, base].join(' ')
}

export function sameConfig(a: GameConfig, b: GameConfig): boolean {
  return (
    a.variant === b.variant &&
    a.boards === b.boards &&
    a.bomb === b.bomb &&
    a.ante === b.ante &&
    a.sb === b.sb &&
    a.bb === b.bb
  )
}
