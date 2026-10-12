import { SUIT_SYMBOL, isRed, rankLabel } from '../lib/cards'

type Size = 'sm' | 'md' | 'lg'

const SIZE: Record<Size, string> = {
  sm: 'h-9 w-7 text-xs',
  md: 'h-12 w-9 text-base',
  lg: 'h-16 w-12 text-xl',
}

export function CardChip({ code, size = 'md', dim = false }: { code: string; size?: Size; dim?: boolean }) {
  return (
    <span
      className={`inline-flex flex-col items-center justify-center rounded-md bg-white font-bold leading-none shadow ${SIZE[size]} ${
        isRed(code) ? 'text-red-600' : 'text-gray-900'
      } ${dim ? 'opacity-40' : ''}`}
    >
      <span>{rankLabel(code)}</span>
      <span>{SUIT_SYMBOL[code[1]]}</span>
    </span>
  )
}

export function CardRow({ cards, size = 'md', dim = false }: { cards: string[]; size?: Size; dim?: boolean }) {
  return (
    <span className="inline-flex gap-1">
      {cards.map((c) => (
        <CardChip key={c} code={c} size={size} dim={dim} />
      ))}
    </span>
  )
}
