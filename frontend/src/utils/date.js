const businessDateFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'
})

export function businessDateParts(date = new Date()) {
  const parts = Object.fromEntries(businessDateFormatter.formatToParts(date).map(part => [part.type, part.value]))
  return { year: Number(parts.year), month: Number(parts.month), day: Number(parts.day) }
}

export function businessDate(date = new Date()) {
  const { year, month, day } = businessDateParts(date)
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

export function shiftBusinessDate(value, days) {
  const [year, month, day] = value.split('-').map(Number)
  return businessDate(new Date(Date.UTC(year, month - 1, day + days)))
}

export function formatBusinessTimestamp(value) {
  if (!value) return ''
  const timestamp = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`
  const date = new Date(timestamp)
  if (Number.isNaN(date.valueOf())) return ''
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
  }).formatToParts(date).map(part => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`
}
