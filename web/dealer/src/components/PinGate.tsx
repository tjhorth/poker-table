import { useState } from 'react'

const PIN = String(import.meta.env.VITE_DEALER_PIN ?? '1234')

// Keys are laid out like the iPhone calculator: 7-8-9 on top, a wide 0 at the
// bottom left, round dark keys for digits and a light grey key for delete.
const DIGIT_ROWS = [
  ['7', '8', '9'],
  ['4', '5', '6'],
  ['1', '2', '3'],
]

const DIGIT_KEY =
  'flex items-center justify-center rounded-full bg-[#333333] text-4xl font-light text-white active:bg-[#737373]'

// A guard against accidental taps, not real security.
export function PinGate({ onUnlock }: { onUnlock: () => void }) {
  const [entry, setEntry] = useState('')
  const [wrong, setWrong] = useState(false)

  const press = (digit: string) => {
    const next = (entry + digit).slice(0, PIN.length)
    setWrong(false)
    setEntry(next)
    if (next.length === PIN.length) {
      if (next === PIN) {
        onUnlock()
      } else {
        setWrong(true)
        window.setTimeout(() => setEntry(''), 400)
      }
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-xs flex-col items-center gap-6 px-4 py-6 text-white">
      <h2 className="text-2xl font-semibold">Enter PIN</h2>
      <div className="flex gap-4" aria-live="polite">
        {Array.from({ length: PIN.length }, (_, i) => (
          <span
            key={i}
            className={`h-4 w-4 rounded-full border-2 ${
              wrong ? 'border-red-400 bg-red-400' : i < entry.length ? 'border-white bg-white' : 'border-gray-500'
            }`}
          />
        ))}
      </div>

      <div className="grid w-full grid-cols-3 gap-3">
        {DIGIT_ROWS.flat().map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => press(d)}
            className={`${DIGIT_KEY} aspect-square`}
          >
            {d}
          </button>
        ))}

        <button
          type="button"
          onClick={() => press('0')}
          className={`${DIGIT_KEY} col-span-2 justify-start pl-8`}
        >
          0
        </button>
        <button
          type="button"
          onClick={() => {
            setWrong(false)
            setEntry((e) => e.slice(0, -1))
          }}
          aria-label="Delete"
          className="flex aspect-square items-center justify-center rounded-full bg-[#a5a5a5] text-3xl text-black active:bg-[#d9d9d9]"
        >
          ⌫
        </button>
      </div>
    </div>
  )
}
