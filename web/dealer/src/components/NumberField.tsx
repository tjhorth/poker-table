import { useEffect, useState } from 'react'

interface Props {
  label: string
  value: number
  onChange: (n: number) => void
  min?: number
  step?: number
  prefix?: string
}

// A number you can step with big buttons or type on the iPad's number pad.
export function NumberField({ label, value, onChange, min = 0, step = 1, prefix = '$' }: Props) {
  const [text, setText] = useState(String(value))
  useEffect(() => setText(String(value)), [value])

  const commit = (raw: string) => {
    const n = Math.max(min, Math.round(Number(raw)))
    if (Number.isFinite(n)) onChange(n)
    else setText(String(value))
  }

  return (
    <label className="block">
      <span className="mb-1 block text-sm text-gray-300">{label}</span>
      <span className="flex items-stretch gap-2">
        <button
          type="button"
          aria-label={`Decrease ${label}`}
          onClick={() => onChange(Math.max(min, value - step))}
          className="w-12 rounded-lg bg-gray-700 text-2xl font-bold active:bg-gray-600"
        >
          −
        </button>
        <span className="flex min-w-0 flex-1 items-center rounded-lg bg-gray-900 px-3 text-xl">
          <span className="text-gray-400">{prefix}</span>
          <input
            inputMode="numeric"
            value={text}
            onChange={(e) => setText(e.target.value.replace(/[^0-9]/g, ''))}
            onBlur={() => commit(text)}
            onKeyDown={(e) => e.key === 'Enter' && commit(text)}
            className="min-h-12 w-full min-w-0 bg-transparent px-1 text-right font-semibold outline-none"
          />
        </span>
        <button
          type="button"
          aria-label={`Increase ${label}`}
          onClick={() => onChange(value + step)}
          className="w-12 rounded-lg bg-gray-700 text-2xl font-bold active:bg-gray-600"
        >
          +
        </button>
      </span>
    </label>
  )
}
