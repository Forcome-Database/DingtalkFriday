<script setup>
import { computed } from 'vue'
import { CalendarDays, Users } from 'lucide-vue-next'

const props = defineProps({
  /** Daily trip count data from API: { days: { "2026-04-01": 3, ... } } */
  dailyData: {
    type: Object,
    default: () => ({ days: {} })
  },
  /** Currently selected month object { year, month } */
  month: {
    type: Object,
    default: () => ({ year: new Date().getFullYear(), month: new Date().getMonth() + 1 })
  },
  /** Whether data is loading */
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['month-change'])

const months = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
const weekDays = ['一', '二', '三', '四', '五', '六', '日']

/**
 * Maximum count value for the current month, used for heatmap color scaling.
 */
const maxCount = computed(() => {
  const days = props.dailyData?.days
  if (!days || typeof days !== 'object') return 1
  const values = Object.values(days)
  if (values.length === 0) return 1
  return Math.max(1, ...values)
})

/**
 * Build the calendar grid for heatmap display.
 * Returns a 2D array (6 rows x 7 cols) of day objects.
 */
const calendarGrid = computed(() => {
  const days = props.dailyData?.days || {}
  const year = props.month.year
  const month = props.month.month

  const firstDay = new Date(year, month - 1, 1)
  const daysInMonth = new Date(year, month, 0).getDate()

  // Get day of week for the 1st (0=Sun, convert to Mon=0)
  let startWeekday = firstDay.getDay() - 1
  if (startWeekday < 0) startWeekday = 6

  const rows = []
  let dayCounter = 1

  for (let row = 0; row < 6; row++) {
    const week = []
    for (let col = 0; col < 7; col++) {
      const cellIdx = row * 7 + col
      if (cellIdx < startWeekday || dayCounter > daysInMonth) {
        week.push({ day: null, count: 0 })
      } else {
        // Build the date key to look up in the days dict
        const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(dayCounter).padStart(2, '0')}`
        const count = days[dateStr] || 0
        week.push({
          day: dayCounter,
          count,
          isWeekend: col >= 5,
          dateStr,
        })
        dayCounter++
      }
    }
    rows.push(week)
    if (dayCounter > daysInMonth) {
      while (rows.length < 6) {
        rows.push(Array(7).fill({ day: null, count: 0 }))
      }
      break
    }
  }

  return rows
})

/**
 * Days with trip records, sorted by count descending for the side list.
 */
const daysWithTrips = computed(() => {
  const days = props.dailyData?.days || {}
  const entries = Object.entries(days)
    .filter(([, count]) => count > 0)
    .map(([date, count]) => ({ date, count }))
    .sort((a, b) => b.count - a.count)
  return entries
})

/**
 * Get heatmap color class based on count relative to maxCount.
 * Uses orange tones to distinguish from the leave heatmap (blue).
 */
function getHeatColor(count) {
  if (!count || count === 0) return ''
  const ratio = count / maxCount.value
  if (ratio <= 0.25) return 'bg-orange-100 text-orange-700'
  if (ratio <= 0.5) return 'bg-orange-200 text-orange-800'
  if (ratio <= 0.75) return 'bg-orange-300 text-orange-900'
  return 'bg-orange-400 text-white'
}

/**
 * Format date string for table display (e.g. "1日（周一）")
 */
function formatDate(dateStr) {
  const date = new Date(dateStr)
  const day = date.getDate()
  const weekNames = ['日', '一', '二', '三', '四', '五', '六']
  const wd = weekNames[date.getDay()]
  return `${day}日（周${wd}）`
}
</script>

<template>
  <div class="rounded-xl border-[1.5px] border-border-default bg-white">
    <!-- Header: title + month selector -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 sm:px-6 py-4 border-b border-border-default">
      <div class="flex items-center gap-2">
        <CalendarDays :size="18" class="text-accent" />
        <h2 class="text-[15px] font-semibold text-text-primary">每日外出/出差统计</h2>
      </div>
      <div class="flex flex-wrap items-center gap-1">
        <button
          v-for="m in months"
          :key="m"
          class="px-2.5 py-1 text-[12px] rounded-md transition-colors"
          :class="m === month.month
            ? 'bg-accent text-white font-medium'
            : 'text-text-secondary hover:bg-surface'"
          @click="emit('month-change', month.year, m)"
        >
          {{ m }}月
        </button>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex items-center justify-center py-16">
      <svg class="animate-spin h-6 w-6 text-accent" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>

    <!-- Content -->
    <div v-else class="flex flex-col lg:flex-row lg:divide-x divide-border-default">
      <!-- Left: Calendar heatmap -->
      <div class="w-full lg:w-[340px] p-4 sm:p-6 flex-shrink-0">
        <!-- Weekday headers -->
        <div class="grid grid-cols-7 gap-1 mb-1">
          <div
            v-for="wd in weekDays"
            :key="wd"
            class="text-center text-[11px] font-medium text-text-tertiary py-1"
          >
            {{ wd }}
          </div>
        </div>

        <!-- Calendar rows -->
        <div
          v-for="(week, wIdx) in calendarGrid"
          :key="wIdx"
          class="grid grid-cols-7 gap-1 mb-1"
        >
          <div
            v-for="(cell, cIdx) in week"
            :key="cIdx"
            class="aspect-square flex items-center justify-center rounded-md text-[12px] relative group cursor-default"
            :class="[
              cell.day === null ? '' : 'border border-transparent',
              cell.day !== null && cell.count === 0
                ? (cell.isWeekend ? 'text-text-tertiary' : 'text-text-primary')
                : '',
              cell.day !== null ? getHeatColor(cell.count) : ''
            ]"
          >
            {{ cell.day || '' }}
            <!-- Tooltip on hover -->
            <div
              v-if="cell.day !== null && cell.count > 0"
              class="absolute z-10 bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-max max-w-[200px] bg-gray-800 text-white text-[11px] rounded-lg px-3 py-2 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity shadow-lg"
            >
              <div class="font-medium">{{ month.month }}月{{ cell.day }}日 · {{ cell.count }}人外出/出差</div>
            </div>
          </div>
        </div>

        <!-- Legend (orange tones) -->
        <div class="flex items-center gap-3 mt-4 text-[11px] text-text-tertiary">
          <span class="flex items-center gap-1">
            <span class="w-3.5 h-3.5 rounded border border-border-default"></span>
            0人
          </span>
          <span class="flex items-center gap-1">
            <span class="w-3.5 h-3.5 rounded bg-orange-100"></span>
            少
          </span>
          <span class="flex items-center gap-1">
            <span class="w-3.5 h-3.5 rounded bg-orange-200"></span>
          </span>
          <span class="flex items-center gap-1">
            <span class="w-3.5 h-3.5 rounded bg-orange-300"></span>
          </span>
          <span class="flex items-center gap-1">
            <span class="w-3.5 h-3.5 rounded bg-orange-400"></span>
            多
          </span>
        </div>
      </div>

      <!-- Right: Table of days with trip records -->
      <div class="flex-1 flex flex-col min-w-0 border-t lg:border-t-0">
        <div class="px-4 py-3 border-b border-border-default">
          <div class="grid grid-cols-[110px_60px_1fr] text-[12px] font-medium text-text-tertiary">
            <span>日期</span>
            <span class="text-center">人数</span>
            <span class="pl-3">统计</span>
          </div>
        </div>

        <div class="overflow-y-auto max-h-[400px]">
          <div
            v-for="day in daysWithTrips"
            :key="day.date"
            class="grid grid-cols-[110px_60px_1fr] items-center px-4 py-2.5 border-b border-border-default/50 text-[13px] hover:bg-surface/50 transition-colors"
          >
            <span class="text-text-primary font-medium">{{ formatDate(day.date) }}</span>
            <span class="text-center">
              <span class="inline-flex items-center justify-center min-w-[24px] px-1.5 py-0.5 rounded-full text-[12px] font-semibold bg-orange-50 text-orange-600">
                {{ day.count }}
              </span>
            </span>
            <div class="pl-3 text-[12px] text-text-tertiary">
              {{ day.count }}人外出/出差
            </div>
          </div>

          <!-- Empty state -->
          <div
            v-if="daysWithTrips.length === 0"
            class="flex flex-col items-center justify-center py-12 text-text-tertiary"
          >
            <Users :size="32" class="mb-2 opacity-30" />
            <span class="text-sm">本月无外出/出差记录</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
