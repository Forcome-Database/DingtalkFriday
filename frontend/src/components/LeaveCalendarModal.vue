<script setup>
import { computed } from 'vue'
import { X, Clock, CheckCircle, AlertCircle, XCircle } from 'lucide-vue-next'

const props = defineProps({
  /** Whether the modal is visible */
  visible: {
    type: Boolean,
    default: false
  },
  /** Daily detail data from API */
  data: {
    type: Object,
    default: null
  },
  /** Whether data is loading */
  loading: {
    type: Boolean,
    default: false
  },
  /** Selected cell info */
  selectedCell: {
    type: Object,
    default: () => ({
      employeeId: '',
      employeeName: '',
      dept: '',
      year: 2025,
      month: 1
    })
  }
})

const emit = defineEmits(['close'])

/** Leave type color mapping */
const leaveTypeColors = {
  '年假': { bg: 'bg-leave-annual-bg', text: 'text-leave-annual-text', border: 'border-[#93C5FD]' },
  '事假': { bg: 'bg-leave-personal-bg', text: 'text-leave-personal-text', border: 'border-[#FCD34D]' },
  '病假': { bg: 'bg-leave-sick-bg', text: 'text-leave-sick-text', border: 'border-[#FCA5A5]' },
  '调休': { bg: 'bg-leave-comp-bg', text: 'text-leave-comp-text', border: 'border-[#6EE7B7]' }
}

/** Status badge configuration */
const statusConfig = {
  '已审批': { icon: CheckCircle, class: 'text-green-600 bg-green-50' },
  '审批中': { icon: AlertCircle, class: 'text-yellow-600 bg-yellow-50' },
  '已驳回': { icon: XCircle, class: 'text-red-600 bg-red-50' }
}

/** Weekday headers */
const weekDays = ['一', '二', '三', '四', '五', '六', '日']

/**
 * Get the first character of a name for the avatar
 */
function getInitial(name) {
  return name ? name.charAt(0) : '?'
}

/**
 * Build the calendar grid for the selected month.
 * Returns a 2D array (6 rows x 7 cols) of day objects.
 */
const calendarGrid = computed(() => {
  const { year, month } = props.selectedCell
  if (!year || !month) return []

  const firstDay = new Date(year, month - 1, 1)
  const daysInMonth = new Date(year, month, 0).getDate()

  // Get day of week for the 1st (0=Sun, convert to Mon=0)
  let startWeekday = firstDay.getDay() - 1
  if (startWeekday < 0) startWeekday = 6

  // Build a set of leave dates for quick lookup
  const leaveDateMap = new Map()
  if (props.data?.records) {
    for (const record of props.data.records) {
      const day = parseInt(record.date.split('-')[2], 10)
      if (!leaveDateMap.has(day)) {
        leaveDateMap.set(day, [])
      }
      leaveDateMap.get(day).push(record)
    }
  }

  const rows = []
  let dayCounter = 1

  for (let row = 0; row < 6; row++) {
    const week = []
    for (let col = 0; col < 7; col++) {
      const cellIdx = row * 7 + col
      if (cellIdx < startWeekday || dayCounter > daysInMonth) {
        // Empty cell (before month start or after month end)
        week.push({ day: null, isWeekend: false, hasLeave: false, isFullDay: false })
      } else {
        const day = dayCounter
        const isWeekend = col >= 5
        const records = leaveDateMap.get(day) || []
        const hasLeave = records.length > 0
        // Full day = 8 hours total for that day
        const totalHours = records.reduce((s, r) => s + r.hours, 0)
        const isFullDay = hasLeave && totalHours >= 8

        week.push({ day, isWeekend, hasLeave, isFullDay, records })
        dayCounter++
      }
    }
    rows.push(week)
    // Stop adding rows if we've placed all days
    if (dayCounter > daysInMonth) {
      // Add any remaining empty rows up to 6 total for consistent layout
      while (rows.length < 6) {
        rows.push(Array(7).fill({ day: null, isWeekend: false, hasLeave: false, isFullDay: false }))
      }
      break
    }
  }

  return rows
})

/**
 * Format a date string (YYYY-MM-DD) to a display string with weekday
 */
function formatDate(dateStr) {
  const date = new Date(dateStr)
  const month = date.getMonth() + 1
  const day = date.getDate()
  const weekNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const weekDay = weekNames[date.getDay()]
  return `${month}月${day}日（${weekDay}）`
}

/**
 * Format duration hours to a readable string
 */
function formatDuration(hours) {
  if (hours >= 8) {
    const days = Math.round(hours / 8 * 10) / 10
    return `全天 \u00B7 ${hours}小时`
  }
  if (hours >= 4) {
    return `半天 \u00B7 ${hours}小时`
  }
  return `${hours}小时`
}

/**
 * Get the color config for a leave type
 */
function getTypeColor(type) {
  return leaveTypeColors[type] || { bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-300' }
}

/**
 * Get the status config for a status string
 */
function getStatusConfig(status) {
  return statusConfig[status] || statusConfig['已审批']
}

/**
 * Close modal when clicking the overlay
 */
function onOverlayClick(event) {
  if (event.target === event.currentTarget) {
    emit('close')
  }
}
</script>

<template>
  <Teleport to="body">
    <!-- Overlay -->
    <Transition name="fade">
      <div
        v-if="visible"
        class="fixed inset-0 bg-black/40 z-50"
        @click="onOverlayClick"
      >
        <!-- Slide-in panel -->
        <Transition name="slide">
          <div
            v-if="visible"
            class="absolute right-0 top-0 bottom-0 w-full sm:w-[480px] max-w-full bg-white shadow-2xl flex flex-col"
            @click.stop
          >
            <!-- Panel header -->
            <div class="flex items-start justify-between p-4 sm:p-6 pb-4 border-b border-border-default">
              <div class="flex items-center gap-3">
                <!-- Employee avatar -->
                <div class="w-11 h-11 rounded-full bg-accent text-white text-lg font-semibold flex items-center justify-center flex-shrink-0">
                  {{ getInitial(selectedCell.employeeName) }}
                </div>
                <div>
                  <div class="text-base font-semibold text-text-primary">
                    {{ selectedCell.employeeName }}
                    <span class="text-text-tertiary font-normal"> &middot; </span>
                    <span class="text-sm text-text-secondary font-normal">{{ selectedCell.dept }}</span>
                  </div>
                  <div class="text-[13px] text-text-secondary mt-0.5">
                    {{ selectedCell.year }}年{{ selectedCell.month }}月 请假明细
                  </div>
                </div>
              </div>
              <!-- Close button -->
              <button
                class="w-8 h-8 flex items-center justify-center rounded-md hover:bg-surface text-text-tertiary hover:text-text-primary transition-colors"
                @click="emit('close')"
              >
                <X :size="20" />
              </button>
            </div>

            <!-- Panel body (scrollable) -->
            <div class="flex-1 overflow-y-auto p-4 sm:p-6">
              <!-- Loading state -->
              <div v-if="loading" class="flex items-center justify-center py-20">
                <svg class="animate-spin h-6 w-6 text-accent" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>

              <template v-else-if="data">
                <!-- Monthly calendar grid -->
                <div class="mb-6">
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
                    class="grid grid-cols-7 gap-1"
                  >
                    <div
                      v-for="(cell, cIdx) in week"
                      :key="cIdx"
                      class="aspect-square flex items-center justify-center rounded-md text-[13px] relative"
                      :class="[
                        cell.day === null ? '' : '',
                        cell.isWeekend && cell.day ? 'text-text-tertiary' : '',
                        cell.hasLeave && cell.isFullDay ? 'bg-leave-annual-bg text-leave-annual-text font-semibold' : '',
                        cell.hasLeave && !cell.isFullDay ? 'bg-leave-annual-bg/50 border border-dashed border-accent/40 text-accent font-medium' : '',
                        !cell.hasLeave && cell.day ? 'text-text-primary' : ''
                      ]"
                    >
                      {{ cell.day || '' }}
                    </div>
                  </div>

                  <!-- Legend -->
                  <div class="flex items-center gap-4 mt-3 text-[11px] text-text-tertiary">
                    <span class="flex items-center gap-1">
                      <span class="w-4 h-4 rounded bg-leave-annual-bg"></span>
                      全天请假
                    </span>
                    <span class="flex items-center gap-1">
                      <span class="w-4 h-4 rounded bg-leave-annual-bg/50 border border-dashed border-accent/40"></span>
                      不足全天
                    </span>
                    <span class="flex items-center gap-1">
                      <span class="w-4 h-4 rounded border border-border-default"></span>
                      无请假
                    </span>
                  </div>
                </div>

                <!-- Leave records list -->
                <div class="space-y-3">
                  <h3 class="text-[13px] font-semibold text-text-primary mb-2">请假记录</h3>

                  <div
                    v-for="(record, idx) in data.records"
                    :key="idx"
                    class="border border-border-default rounded-lg p-3"
                  >
                    <div class="flex items-start justify-between mb-2">
                      <div>
                        <div class="text-sm font-medium text-text-primary">
                          {{ formatDate(record.date) }}
                        </div>
                        <div class="flex items-center gap-1.5 mt-1 text-[13px] text-text-secondary">
                          <Clock :size="13" class="text-text-tertiary" />
                          <span>{{ record.startTime }} - {{ record.endTime }}</span>
                          <span class="text-text-tertiary">&middot;</span>
                          <span>{{ formatDuration(record.hours) }}</span>
                        </div>
                      </div>
                      <!-- Status badge -->
                      <div
                        class="flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium"
                        :class="getStatusConfig(record.status).class"
                      >
                        <component :is="getStatusConfig(record.status).icon" :size="12" />
                        {{ record.status }}
                      </div>
                    </div>
                    <!-- Leave type tag -->
                    <span
                      class="inline-flex items-center px-2.5 py-0.5 rounded text-[12px] font-medium"
                      :class="[getTypeColor(record.leaveType).bg, getTypeColor(record.leaveType).text]"
                    >
                      {{ record.leaveType }}
                    </span>
                  </div>

                  <!-- Empty state for records -->
                  <div
                    v-if="data.records && data.records.length === 0"
                    class="text-center py-8 text-text-tertiary text-sm"
                  >
                    本月无请假记录
                  </div>
                </div>
              </template>
            </div>

            <!-- Panel footer: summary -->
            <div
              v-if="data?.summary"
              class="border-t border-border-default px-6 py-4 bg-surface"
            >
              <div class="flex items-center justify-between">
                <span class="text-[13px] font-medium text-text-secondary">本月合计</span>
                <span class="text-base font-semibold text-accent">
                  {{ data.summary.totalDays }} 天 &middot; {{ data.summary.totalHours }} 小时
                </span>
              </div>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>
