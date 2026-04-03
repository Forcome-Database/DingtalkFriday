<script setup>
import { computed } from 'vue'
import { X, Clock, CheckCircle, Briefcase, MapPin } from 'lucide-vue-next'

const props = defineProps({
  visible: { type: Boolean, default: false },
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  selectedCell: {
    type: Object,
    default: () => ({ employeeId: '', employeeName: '', dept: '', year: 2026, month: 1 })
  }
})

const emit = defineEmits(['close'])

/** Trip type color mapping */
const tripTypeColors = {
  '出差': { bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-300' },
  '外出': { bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-300' },
}

const weekDays = ['一', '二', '三', '四', '五', '六', '日']

function getInitial(name) {
  return name ? name.charAt(0) : '?'
}

const calendarGrid = computed(() => {
  const { year, month } = props.selectedCell
  if (!year || !month) return []

  const firstDay = new Date(year, month - 1, 1)
  const daysInMonth = new Date(year, month, 0).getDate()

  let startWeekday = firstDay.getDay() - 1
  if (startWeekday < 0) startWeekday = 6

  // Build a map of trip dates
  const tripDateMap = new Map()
  if (props.data?.records) {
    for (const record of props.data.records) {
      const day = parseInt(record.date.split('-')[2], 10)
      if (!tripDateMap.has(day)) {
        tripDateMap.set(day, [])
      }
      tripDateMap.get(day).push(record)
    }
  }

  const rows = []
  let dayCounter = 1

  for (let row = 0; row < 6; row++) {
    const week = []
    for (let col = 0; col < 7; col++) {
      const cellIdx = row * 7 + col
      if (cellIdx < startWeekday || dayCounter > daysInMonth) {
        week.push({ day: null, isWeekend: false, hasTrip: false, isFullDay: false })
      } else {
        const day = dayCounter
        const isWeekend = col >= 5
        const records = tripDateMap.get(day) || []
        const hasTrip = records.length > 0
        const totalHours = records.reduce((s, r) => s + (r.hours || 0), 0)
        const isFullDay = hasTrip && totalHours >= 8

        week.push({ day, isWeekend, hasTrip, isFullDay, records })
        dayCounter++
      }
    }
    rows.push(week)
    if (dayCounter > daysInMonth) {
      while (rows.length < 6) {
        rows.push(Array(7).fill({ day: null, isWeekend: false, hasTrip: false, isFullDay: false }))
      }
      break
    }
  }

  return rows
})

function formatDate(dateStr) {
  const date = new Date(dateStr)
  const month = date.getMonth() + 1
  const day = date.getDate()
  const weekNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const weekDay = weekNames[date.getDay()]
  return `${month}月${day}日（${weekDay}）`
}

function formatDuration(hours) {
  if (hours >= 8) return `全天 \u00B7 ${hours}小时`
  if (hours >= 4) return `半天 \u00B7 ${hours}小时`
  return `${hours}小时`
}

function getTypeColor(type) {
  return tripTypeColors[type] || { bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-300' }
}

function onOverlayClick(event) {
  if (event.target === event.currentTarget) {
    emit('close')
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="visible"
        class="fixed inset-0 bg-black/40 z-50"
        @click="onOverlayClick"
      >
        <Transition name="slide">
          <div
            v-if="visible"
            class="absolute right-0 top-0 bottom-0 w-full sm:w-[480px] max-w-full bg-white shadow-2xl flex flex-col"
            @click.stop
          >
            <!-- Header -->
            <div class="flex items-start justify-between p-4 sm:p-6 pb-4 border-b border-border-default">
              <div class="flex items-center gap-3">
                <div class="w-11 h-11 rounded-full bg-orange-500 text-white text-lg font-semibold flex items-center justify-center flex-shrink-0">
                  {{ getInitial(selectedCell.employeeName) }}
                </div>
                <div>
                  <div class="text-base font-semibold text-text-primary">
                    {{ selectedCell.employeeName }}
                    <span class="text-text-tertiary font-normal"> &middot; </span>
                    <span class="text-sm text-text-secondary font-normal">{{ selectedCell.dept }}</span>
                  </div>
                  <div class="text-[13px] text-text-secondary mt-0.5">
                    {{ selectedCell.year }}年{{ selectedCell.month }}月 外出/出差明细
                  </div>
                </div>
              </div>
              <button
                class="w-8 h-8 flex items-center justify-center rounded-md hover:bg-surface text-text-tertiary hover:text-text-primary transition-colors"
                @click="emit('close')"
              >
                <X :size="20" />
              </button>
            </div>

            <!-- Body -->
            <div class="flex-1 overflow-y-auto p-4 sm:p-6">
              <!-- Loading -->
              <div v-if="loading" class="flex items-center justify-center py-20">
                <svg class="animate-spin h-6 w-6 text-orange-500" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>

              <template v-else-if="data">
                <!-- Calendar grid -->
                <div class="mb-6">
                  <div class="grid grid-cols-7 gap-1 mb-1">
                    <div
                      v-for="wd in weekDays"
                      :key="wd"
                      class="text-center text-[11px] font-medium text-text-tertiary py-1"
                    >{{ wd }}</div>
                  </div>

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
                        cell.isWeekend && cell.day ? 'text-text-tertiary' : '',
                        cell.hasTrip && cell.isFullDay ? 'bg-orange-100 text-orange-700 font-semibold' : '',
                        cell.hasTrip && !cell.isFullDay ? 'bg-orange-50 border border-dashed border-orange-300 text-orange-600 font-medium' : '',
                        !cell.hasTrip && cell.day ? 'text-text-primary' : ''
                      ]"
                    >
                      {{ cell.day || '' }}
                    </div>
                  </div>

                  <!-- Legend -->
                  <div class="flex items-center gap-4 mt-3 text-[11px] text-text-tertiary">
                    <span class="flex items-center gap-1">
                      <span class="w-4 h-4 rounded bg-orange-100"></span>
                      全天
                    </span>
                    <span class="flex items-center gap-1">
                      <span class="w-4 h-4 rounded bg-orange-50 border border-dashed border-orange-300"></span>
                      不足全天
                    </span>
                    <span class="flex items-center gap-1">
                      <span class="w-4 h-4 rounded border border-border-default"></span>
                      无记录
                    </span>
                  </div>
                </div>

                <!-- Records list -->
                <div class="space-y-3">
                  <h3 class="text-[13px] font-semibold text-text-primary mb-2">外出/出差记录</h3>

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
                      <div
                        class="flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium text-green-600 bg-green-50"
                      >
                        <CheckCircle :size="12" />
                        已审批
                      </div>
                    </div>
                    <!-- Type tag -->
                    <span
                      class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[12px] font-medium"
                      :class="[getTypeColor(record.leaveType || record.tagName).bg, getTypeColor(record.leaveType || record.tagName).text]"
                    >
                      <component :is="(record.leaveType || record.tagName) === '出差' ? Briefcase : MapPin" :size="12" />
                      {{ record.leaveType || record.tagName }}
                    </span>
                  </div>

                  <div
                    v-if="data.records && data.records.length === 0"
                    class="text-center py-8 text-text-tertiary text-sm"
                  >
                    本月无外出/出差记录
                  </div>
                </div>
              </template>
            </div>

            <!-- Footer: summary -->
            <div
              v-if="data?.summary"
              class="border-t border-border-default px-6 py-4 bg-surface"
            >
              <div class="flex items-center justify-between">
                <span class="text-[13px] font-medium text-text-secondary">本月合计</span>
                <span class="text-base font-semibold text-orange-600">
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

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.slide-enter-active, .slide-leave-active { transition: transform 0.3s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>
