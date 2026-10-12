export function money(n: number): string {
  return '$' + n.toLocaleString('en-US')
}

export function signedMoney(n: number): string {
  return (n >= 0 ? '+' : '-') + money(Math.abs(n))
}

export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}
