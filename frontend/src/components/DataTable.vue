<script setup>
import { computed } from 'vue'
import { Calendar, Clock, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-vue-next'
import Pagination from './Pagination.vue'

const props = defineProps({
  /** Array of employee leave data rows */
  tableData: {
    type: Array,
    default: () => []
  },
  /** Summary row object with aggregated values */
  summaryRow: {
    type: Object,
    default: null
  },
  /** Total record count for display */
  total: {
    type: Number,
    default: 0
  },
  /** Current display unit: 'day' or 'hour' */
  unit: {
    type: String,
    default: 'day'
  },
  /** Current sort field */
  sortBy: {
    type: String,
    default: 'name'
  },
  /** Current sort order: '', 'asc', 'desc' */
  sortOrder: {
    type: String,
    default: ''
  },
  /** Current page */
  page: {
    type: Number,
    default: 1
  },
  /** Page size */
  pageSize: {
    type: Number,
    default: 10
  },
  /** Whether data is loading */
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['unit-change', 'sort', 'page-change', 'page-size-change', 'cell-click'])

/** Month header labels */
const months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

/**
 * Format a cell value for display.
 * Returns '-' for zero/null values, otherwise formats to 1 decimal place.
 */
function formatValue(val) {
  if (val === null || val === undefined || val === 0) return '-'
  return Number(val).toFixed(1)
}

/**
 * Determine the CSS class for a cell value.
 * Non-zero values get bold styling with accent color.
 */
function cellClass(val) {
  if (!val || val === 0) return 'text-text-tertiary'
  return 'font-semibold text-accent'
}

/**
 * Check if a cell has data and is clickable
 */
function isClickable(val) {
  return val !== null && val !== undefined && val !== 0
}

/**
 * Handle clicking on a data cell to open the detail modal
 */
function onCellClick(employee, monthIndex) {
  const val = employee.months[monthIndex]
  if (!isClickable(val)) return
  emit('cell-click', {
    employeeId: employee.employeeId,
    name: employee.name,
    dept: employee.dept,
    month: monthIndex + 1
  })
}

/**
 * Get the first character of the employee name for the avatar
 */
function getInitial(name) {
  return name ? name.charAt(0) : '?'
}
</script>

<template>
  <div class="rounded-xl border-[1.5px] border-border-default overflow-hidden">
    <!-- Table info bar -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:h-12 px-4 py-2 sm:py-0 bg-white">
      <!-- Left: Record count -->
      <span class="text-xs sm:text-[13px] font-medium text-text-secondary">
        共 {{ total }} 条记录
      </span>

      <div class="flex items-center gap-4">
        <!-- Unit switch (segmented control) -->
        <div class="flex items-center h-8 border-[1.5px] border-border-default rounded-lg p-[3px]">
          <button
            class="flex items-center gap-1 px-3 py-1 rounded-md text-xs font-semibold transition-all"
            :class="unit === 'day'
              ? 'bg-accent text-white'
              : 'text-text-secondary hover:bg-surface'"
            @click="emit('unit-change', 'day')"
          >
            <Calendar :size="12" />
            <span>按天</span>
          </button>
          <button
            class="flex items-center gap-1 px-3 py-1 rounded-md text-xs font-medium transition-all"
            :class="unit === 'hour'
              ? 'bg-accent text-white'
              : 'text-text-secondary hover:bg-surface'"
            @click="emit('unit-change', 'hour')"
          >
            <Clock :size="12" />
            <span>按小时</span>
          </button>
        </div>

        <!-- Legend (hidden on mobile) -->
        <div class="hidden md:flex items-center gap-3 text-[11px] text-text-tertiary">
          <span class="flex items-center gap-1">
            <span class="w-2.5 h-2.5 rounded-sm bg-leave-annual-bg border border-[#93C5FD]"></span>
            年假
          </span>
          <span class="flex items-center gap-1">
            <span class="w-2.5 h-2.5 rounded-sm bg-leave-personal-bg border border-[#FCD34D]"></span>
            事假
          </span>
          <span class="flex items-center gap-1">
            <span class="w-2.5 h-2.5 rounded-sm bg-leave-sick-bg border border-[#FCA5A5]"></span>
            病假
          </span>
          <span class="flex items-center gap-1">
            <span class="w-2.5 h-2.5 rounded-sm bg-leave-comp-bg border border-[#6EE7B7]"></span>
            调休
          </span>
        </div>
      </div>
    </div>

    <!-- Table wrapper with horizontal scroll -->
    <div class="overflow-x-auto relative">
      <!-- Loading overlay -->
      <div
        v-if="loading"
        class="absolute inset-0 bg-white/60 flex items-center justify-center z-10"
      >
        <div class="flex items-center gap-2 text-sm text-text-secondary">
          <svg class="animate-spin h-5 w-5 text-accent" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span>加载中...</span>
        </div>
      </div>

      <table class="w-full text-sm">
        <!-- Table header -->
        <thead>
          <tr class="bg-surface border-t border-border-default">
            <th class="sticky left-0 z-[2] bg-surface w-[70px] sm:w-[90px] min-w-[70px] sm:min-w-[90px] px-2 sm:px-3 py-3 text-left text-xs sm:text-[13px] font-medium text-text-secondary">
              姓名
            </th>
            <th class="sticky left-[70px] sm:left-[90px] z-[2] bg-surface w-[70px] sm:w-[90px] min-w-[70px] sm:min-w-[90px] px-2 sm:px-3 py-3 text-left text-xs sm:text-[13px] font-medium text-text-secondary border-r border-border-default">
              部门
            </th>
            <th
              v-for="(m, idx) in months"
              :key="idx"
              class="px-2 py-3 text-center text-xs sm:text-[13px] font-medium text-text-secondary min-w-[52px] sm:min-w-[64px]"
            >
              {{ m }}
            </th>
            <!-- Total column header with sort -->
            <th
              class="px-3 py-3 text-center text-[13px] font-semibold text-accent bg-highlight min-w-[70px] cursor-pointer select-none hover:bg-blue-100 transition-colors"
              @click="emit('sort')"
            >
              <div class="flex items-center justify-center gap-1">
                <span>合计</span>
                <ArrowUp v-if="sortBy === 'total' && sortOrder === 'asc'" :size="14" />
                <ArrowDown v-else-if="sortBy === 'total' && sortOrder === 'desc'" :size="14" />
                <ArrowUpDown v-else :size="14" class="text-text-tertiary" />
              </div>
            </th>
          </tr>
        </thead>

        <tbody>
          <!-- Empty state -->
          <tr v-if="tableData.length === 0 && !loading">
            <td :colspan="15" class="py-16 text-center text-text-tertiary text-sm">
              暂无数据，请调整筛选条件后查询
            </td>
          </tr>

          <!-- Data rows -->
          <tr
            v-for="(row, rowIdx) in tableData"
            :key="row.employeeId"
            class="border-t border-border-default hover:bg-surface/50 transition-colors"
          >
            <!-- Name column (sticky) -->
            <td class="sticky left-0 z-[1] bg-white px-2 sm:px-3 py-3">
              <div class="flex items-center gap-1.5 sm:gap-2">
                <div
                  class="w-6 h-6 sm:w-7 sm:h-7 rounded-full bg-blue-50 text-accent text-xs font-semibold flex items-center justify-center flex-shrink-0"
                >
                  {{ getInitial(row.name) }}
                </div>
                <span class="text-xs sm:text-sm font-medium text-text-primary truncate">{{ row.name }}</span>
              </div>
            </td>
            <!-- Department column (sticky) -->
            <td class="sticky left-[70px] sm:left-[90px] z-[1] bg-white px-2 sm:px-3 py-3 text-xs sm:text-sm text-text-secondary border-r border-border-default truncate">
              {{ row.dept }}
            </td>
            <!-- Monthly cells -->
            <td
              v-for="(val, mIdx) in row.months"
              :key="mIdx"
              class="px-2 py-3 text-center text-xs sm:text-sm transition-colors"
              :class="[
                cellClass(val),
                isClickable(val) ? 'cursor-pointer hover:bg-highlight' : ''
              ]"
              @click="onCellClick(row, mIdx)"
            >
              {{ formatValue(val) }}
            </td>
            <!-- Total column -->
            <td class="px-3 py-3 text-center text-xs sm:text-sm font-bold text-accent bg-highlight">
              {{ formatValue(row.total) }}
            </td>
          </tr>

          <!-- Summary row -->
          <tr
            v-if="summaryRow && tableData.length > 0"
            class="border-t-2 border-accent/20 bg-highlight font-semibold"
          >
            <td class="sticky left-0 z-[1] bg-highlight px-2 sm:px-3 py-3 text-xs sm:text-sm text-accent">
              合计
            </td>
            <td class="sticky left-[70px] sm:left-[90px] z-[1] bg-highlight px-2 sm:px-3 py-3 text-xs sm:text-sm text-accent border-r border-border-default">
              {{ summaryRow.personCount }} 人
            </td>
            <td
              v-for="(val, mIdx) in summaryRow.months"
              :key="mIdx"
              class="px-2 py-3 text-center text-xs sm:text-sm text-accent"
            >
              {{ formatValue(val) }}
            </td>
            <td class="px-3 py-3 text-center text-xs sm:text-sm font-bold text-accent bg-blue-100">
              {{ formatValue(summaryRow.total) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="border-t border-border-default bg-white">
      <Pagination
        :page="page"
        :page-size="pageSize"
        :total="total"
        @page-change="(p) => emit('page-change', p)"
        @page-size-change="(s) => emit('page-size-change', s)"
      />
    </div>
  </div>
</template>
