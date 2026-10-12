export const SUIT_SYMBOL: Record<string, string> = { s: '♠', h: '♥', d: '♦', c: '♣' }

export function rankLabel(code: string): string {
  return code[0] === 'T' ? '10' : code[0]
}

export function isRed(code: string): boolean {
  return code[1] === 'h' || code[1] === 'd'
}
