import { useState } from 'react'
import {
  ChevronLeft, ChevronRight, Plus, X, User,
  RotateCcw, Mountain, AlertCircle, GripVertical, Check,
} from 'lucide-react'

// ── Date helpers ──────────────────────────────────────────────────────────────
function getMonday(date) {
  const d = new Date(date)
  const day = d.getDay()
  const diff = d.getDate() - day + (day === 0 ? -6 : 1)
  d.setDate(diff)
  d.setHours(0, 0, 0, 0)
  return d
}

function addDays(date, n) {
  const d = new Date(date)
  d.setDate(d.getDate() + n)
  return d
}

function fmt(date) {
  return `${date.getDate()}.${date.getMonth() + 1}.`
}

function fmtFull(date) {
  return `${date.getDate()}.${date.getMonth() + 1}.${date.getFullYear()}`
}

function weekKey(monday) {
  return monday.toISOString().slice(0, 10)
}

// ── Constants ─────────────────────────────────────────────────────────────────
const DEMO_CLIMBERS = [
  'Jan Novák', 'Petra Svobodová', 'Martin Horák',
  'Lucie Krejčí', 'Tomáš Blažek', 'Anna Dvořák',
]
const EMPTY = [null, null, null, null]

const SESSIONS = [
  { id: 'monday',    dayOffset: 0, label: 'Pondělí', type: 'Lanovka', theme: 'blue' },
  { id: 'wednesday', dayOffset: 2, label: 'Středa',  type: 'Limit',   theme: 'orange' },
]

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  const [climbers, setClimbers] = useState(DEMO_CLIMBERS)
  const [newName, setNewName]   = useState('')
  const [offset, setOffset]     = useState(0)
  const [data, setData]         = useState({})
  const [sel, setSel]           = useState(null)   // selected climber name
  const [drag, setDrag]         = useState(null)   // { from, climber, session?, idx? }
  const [flash, setFlash]       = useState(null)   // session id with conflict flash

  // Current week anchor
  const monday = addDays(getMonday(new Date()), offset * 7)
  const friday = addDays(monday, 4)
  const key    = weekKey(monday)
  const week   = data[key] ?? { monday: [...EMPTY], wednesday: [...EMPTY] }

  function setWeek(w) {
    setData(d => ({ ...d, [key]: w }))
  }

  // ── Conflict check ───────────────────────────────────────────────────────
  function hasConflict(climber, targetSession) {
    const other = targetSession === 'monday' ? 'wednesday' : 'monday'
    return week[other].includes(climber)
  }

  function triggerFlash(session) {
    setFlash(session)
    setTimeout(() => setFlash(null), 700)
  }

  // ── Assign / remove ──────────────────────────────────────────────────────
  function assign(climber, session, idx) {
    if (week[session][idx] !== null)       return false
    if (week[session].includes(climber))   return false
    if (hasConflict(climber, session)) { triggerFlash(session); return false }
    setWeek({ ...week, [session]: week[session].map((s, i) => i === idx ? climber : s) })
    return true
  }

  function remove(session, idx) {
    const c = week[session][idx]
    setWeek({ ...week, [session]: week[session].map((s, i) => i === idx ? null : s) })
    if (sel === c) setSel(null)
  }

  function clearSession(session) {
    setWeek({ ...week, [session]: [...EMPTY] })
    setSel(null)
  }

  function clearWeek() {
    setData(d => { const n = { ...d }; delete n[key]; return n })
    setSel(null)
  }

  // ── Click interactions ───────────────────────────────────────────────────
  function onSlotClick(session, idx) {
    if (week[session][idx]) {
      remove(session, idx)
    } else if (sel) {
      if (assign(sel, session, idx)) setSel(null)
    }
  }

  function onChipClick(name) {
    setSel(s => s === name ? null : name)
  }

  // ── Climber management ───────────────────────────────────────────────────
  function addClimber() {
    const n = newName.trim()
    if (!n || climbers.includes(n)) return
    setClimbers(c => [...c, n])
    setNewName('')
  }

  function deleteClimber(name) {
    setClimbers(c => c.filter(x => x !== name))
    if (sel === name) setSel(null)
    setData(d => {
      const out = {}
      for (const [k, w] of Object.entries(d)) {
        out[k] = {
          monday:    w.monday.map(s => s === name ? null : s),
          wednesday: w.wednesday.map(s => s === name ? null : s),
        }
      }
      return out
    })
  }

  // ── Drag & drop ──────────────────────────────────────────────────────────
  function onDragStartPool(name) {
    setDrag({ from: 'pool', climber: name })
    setSel(null)
  }

  function onDragStartSlot(session, idx, name) {
    setDrag({ from: 'slot', climber: name, session, idx })
  }

  function onDropSlot(session, idx) {
    if (!drag) return
    const { from, climber, session: src, idx: srcIdx } = drag
    setDrag(null)

    if (from === 'pool') {
      assign(climber, session, idx)
    } else {
      // slot → slot
      if (src === session) {
        // reorder within same session
        if (idx === srcIdx || week[session][idx] !== null) return
        const slots = [...week[session]]
        slots[srcIdx] = null
        slots[idx] = climber
        setWeek({ ...week, [session]: slots })
      } else {
        // cross-session: blocked
        triggerFlash(session)
      }
    }
  }

  function onDropPool() {
    if (drag?.from === 'slot') remove(drag.session, drag.idx)
    setDrag(null)
  }

  const isCurrentWeek = offset === 0

  return (
    <div className="min-h-screen bg-slate-100">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-20 shadow-sm">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center justify-between gap-3">

          {/* Logo */}
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-blue-600 flex-shrink-0 flex items-center justify-center shadow">
              <Mountain className="w-5 h-5 text-white" />
            </div>
            <div className="min-w-0 hidden sm:block">
              <p className="text-base font-bold text-gray-900 leading-none">Stavění tras</p>
              <p className="text-xs text-gray-400 mt-0.5">Týdenní plán stavěčů</p>
            </div>
          </div>

          {/* Week nav */}
          <div className="flex items-center gap-1 flex-shrink-0">
            <button
              onClick={() => setOffset(o => o - 1)}
              className="p-2 rounded-xl hover:bg-gray-100 text-gray-600 transition-colors"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>

            <div className="text-center min-w-[138px] px-1">
              <p className="text-sm font-bold text-gray-900 tabular-nums">
                {fmt(monday)} – {fmt(friday)}{friday.getFullYear()}
              </p>
              <p className={`text-xs font-semibold mt-0.5 ${isCurrentWeek ? 'text-blue-500' : 'text-gray-400'}`}>
                {isCurrentWeek ? 'Aktuální týden' : `Týden ${offset > 0 ? '+' : ''}${offset}`}
              </p>
            </div>

            <button
              onClick={() => setOffset(o => o + 1)}
              className="p-2 rounded-xl hover:bg-gray-100 text-gray-600 transition-colors"
            >
              <ChevronRight className="w-5 h-5" />
            </button>

            {!isCurrentWeek && (
              <button
                onClick={() => setOffset(0)}
                className="ml-1 text-xs font-bold text-blue-600 hover:text-blue-700 px-2.5 py-1.5 rounded-xl hover:bg-blue-50 border border-blue-200 transition-colors"
              >
                Dnes
              </button>
            )}
          </div>
        </div>
      </header>

      {/* ── Main ───────────────────────────────────────────────────────────── */}
      <main className="max-w-2xl mx-auto px-4 py-5 space-y-4 pb-10">

        {/* Session cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {SESSIONS.map(({ id, dayOffset, label, type, theme }) => (
            <SessionCard
              key={id}
              session={id}
              day={label}
              date={addDays(monday, dayOffset)}
              type={type}
              theme={theme}
              slots={week[id]}
              sel={sel}
              flash={flash === id}
              onSlotClick={idx => onSlotClick(id, idx)}
              onDragStartSlot={(idx, name) => onDragStartSlot(id, idx, name)}
              onDragOverSlot={e => e.preventDefault()}
              onDropSlot={idx => onDropSlot(id, idx)}
              onClear={() => clearSession(id)}
            />
          ))}
        </div>

        {/* Climber pool */}
        <div
          className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden"
          onDragOver={e => e.preventDefault()}
          onDrop={onDropPool}
        >
          {/* Pool header */}
          <div className="px-4 pt-4 pb-3 border-b border-gray-100">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-bold text-gray-900 flex items-center gap-2">
                <User className="w-4 h-4 text-gray-400" />
                Stavěči
                <span className="text-xs font-semibold text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                  {climbers.length}
                </span>
              </h2>
              <div className="flex items-center gap-2">
                {sel && (
                  <span className="hidden sm:flex items-center gap-1 text-xs font-semibold text-blue-700 bg-blue-50 border border-blue-100 px-2.5 py-1 rounded-full">
                    <Check className="w-3 h-3" />
                    {sel}
                  </span>
                )}
                <button
                  onClick={clearWeek}
                  className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500 transition-colors py-1"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Resetovat týden</span>
                </button>
              </div>
            </div>

            {/* Add input */}
            <div className="flex gap-2">
              <input
                type="text"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addClimber()}
                placeholder="Jméno nového stavěče..."
                className="flex-1 px-3 py-2 text-sm rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-gray-50"
              />
              <button
                onClick={addClimber}
                className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white text-sm font-bold rounded-xl transition-colors shadow-sm"
              >
                <Plus className="w-4 h-4" />
                <span>Přidat</span>
              </button>
            </div>
          </div>

          {/* Chips area */}
          <div className="px-4 py-3 flex flex-wrap gap-2 min-h-[64px] items-start content-start">
            {climbers.length === 0 ? (
              <p className="text-sm text-gray-400 py-1">
                Přidejte stavěče pomocí pole výše.
              </p>
            ) : (
              climbers.map(name => (
                <ClimberChip
                  key={name}
                  name={name}
                  isSelected={sel === name}
                  inMon={week.monday.includes(name)}
                  inWed={week.wednesday.includes(name)}
                  onClick={() => onChipClick(name)}
                  onRemove={() => deleteClimber(name)}
                  onDragStart={() => onDragStartPool(name)}
                />
              ))
            )}
          </div>

          {/* Drop-to-remove hint */}
          {drag?.from === 'slot' && (
            <div className="mx-4 mb-3 border-2 border-dashed border-red-200 rounded-xl px-4 py-2.5 text-center text-xs font-medium text-red-400 bg-red-50">
              Přetáhněte sem pro odebrání ze slotu
            </div>
          )}

          {/* Selection hint */}
          {sel && (
            <div className="mx-4 mb-3 border border-blue-100 rounded-xl px-4 py-2.5 text-center text-xs font-medium text-blue-600 bg-blue-50">
              Klikněte na volný slot pro přiřazení
              <button
                onClick={() => setSel(null)}
                className="ml-2 underline underline-offset-2 text-blue-400 hover:text-blue-600"
              >
                Zrušit
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

// ── SessionCard ───────────────────────────────────────────────────────────────
function SessionCard({
  session, day, date, type, theme, slots, sel, flash,
  onSlotClick, onDragStartSlot, onDragOverSlot, onDropSlot, onClear,
}) {
  const blue = theme === 'blue'
  const filled = slots.filter(Boolean).length
  const allFilled = filled === 4

  const gradient   = blue ? 'from-blue-600 to-blue-700'   : 'from-orange-500 to-amber-500'
  const emptyBg    = blue ? 'hover:bg-blue-50 border-blue-200 hover:border-blue-400'
                          : 'hover:bg-orange-50 border-orange-200 hover:border-orange-400'
  const filledBg   = blue ? 'bg-blue-50 border-blue-200'  : 'bg-orange-50 border-orange-200'
  const filledText = blue ? 'text-blue-900'                : 'text-orange-900'
  const numEmpty   = blue ? 'bg-blue-100 text-blue-500'   : 'bg-orange-100 text-orange-500'
  const selRing    = blue ? 'ring-2 ring-blue-300 ring-offset-1'
                          : 'ring-2 ring-orange-300 ring-offset-1'

  return (
    <div
      className={`bg-white rounded-2xl overflow-hidden shadow-sm border transition-all duration-300
        ${flash ? 'ring-2 ring-red-400 ring-offset-2 border-red-200' : 'border-gray-200'}
      `}
    >
      {/* Card header */}
      <div className={`bg-gradient-to-br ${gradient} p-4 text-white`}>
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="text-xl font-black leading-none">{day}</h3>
            <p className="text-sm text-white/70 mt-1 font-medium">{fmtFull(date)}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-sm font-bold px-3 py-1 rounded-full transition-colors
              ${allFilled ? 'bg-white text-green-600' : 'bg-white/20 text-white'}`}
            >
              {allFilled ? '✓ ' : ''}{type}
            </span>
            <button
              onClick={onClear}
              title="Vymazat přiřazení"
              className="p-1.5 rounded-lg hover:bg-white/20 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-3 flex items-center gap-2.5">
          <div className="flex-1 bg-white/20 rounded-full h-1.5">
            <div
              className="bg-white rounded-full h-1.5 transition-all duration-500"
              style={{ width: `${(filled / 4) * 100}%` }}
            />
          </div>
          <span className="text-xs text-white/70 font-bold tabular-nums">{filled}/4</span>
        </div>
      </div>

      {/* Slot list */}
      <div className="p-3 space-y-2">
        {slots.map((name, i) => (
          <div
            key={i}
            onClick={() => onSlotClick(i)}
            draggable={!!name}
            onDragStart={name ? () => onDragStartSlot(i, name) : undefined}
            onDragOver={onDragOverSlot}
            onDrop={() => onDropSlot(i)}
            className={`
              flex items-center gap-2.5 px-3 py-2.5 rounded-xl border
              cursor-pointer transition-all duration-150 select-none
              ${name
                ? `${filledBg} ${filledText} hover:bg-red-50 hover:border-red-200 group`
                : `${emptyBg} border-dashed ${sel ? selRing : 'opacity-80'}`
              }
            `}
          >
            {/* Slot number */}
            <span className={`w-5 h-5 rounded-full flex items-center justify-center
              text-xs font-bold flex-shrink-0
              ${name ? 'bg-white/70 text-gray-600' : numEmpty}`}
            >
              {i + 1}
            </span>

            {name ? (
              <>
                <span className="flex-1 text-sm font-semibold truncate">{name}</span>
                <GripVertical className="w-4 h-4 opacity-20 group-hover:opacity-0 flex-shrink-0 cursor-grab transition-opacity" />
                <X className="w-3.5 h-3.5 opacity-0 group-hover:opacity-50 flex-shrink-0 transition-opacity" />
              </>
            ) : (
              <span className="text-xs text-gray-400 font-medium">
                {sel ? `Přiřadit: ${sel}` : 'Volný slot'}
              </span>
            )}
          </div>
        ))}

        {/* Conflict message */}
        {flash && (
          <div className="flex items-center gap-2 text-xs font-semibold text-red-600
            bg-red-50 border border-red-100 rounded-xl px-3 py-2 mt-1"
          >
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
            Stavěč je již přiřazen v tomto týdnu!
          </div>
        )}
      </div>
    </div>
  )
}

// ── ClimberChip ───────────────────────────────────────────────────────────────
function ClimberChip({ name, isSelected, inMon, inWed, onClick, onRemove, onDragStart }) {
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onClick={onClick}
      className={`
        group flex items-center gap-1.5 pl-2.5 pr-1.5 py-1.5 rounded-full border
        text-sm cursor-pointer transition-all duration-150 select-none
        ${isSelected
          ? 'bg-blue-600 border-blue-500 text-white shadow-md scale-[1.03]'
          : 'bg-white border-gray-200 text-gray-700 hover:border-gray-300 hover:shadow-sm'
        }
      `}
    >
      <User className="w-3.5 h-3.5 flex-shrink-0 opacity-50" />
      <span className="font-semibold">{name}</span>

      {inMon && (
        <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold
          ${isSelected ? 'bg-white/20 text-white' : 'bg-blue-100 text-blue-700'}`}
        >
          Po
        </span>
      )}
      {inWed && (
        <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold
          ${isSelected ? 'bg-white/20 text-white' : 'bg-orange-100 text-orange-700'}`}
        >
          St
        </span>
      )}

      <button
        onClick={e => { e.stopPropagation(); onRemove() }}
        className={`ml-0.5 p-0.5 rounded-full transition-colors flex-shrink-0
          ${isSelected
            ? 'text-white/50 hover:text-white hover:bg-white/20'
            : 'text-gray-300 hover:text-red-400 hover:bg-red-50'
          }`}
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  )
}
