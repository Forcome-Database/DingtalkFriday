<script setup>
import { computed } from 'vue'
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-vue-next'
import Pagination from './Pagination.vue'

const props = defineProps({
  /** Array of employee trip data rows */
  tableData: {
    type: Array,
    default: () => []
  },
  /** Summary row object with aggregated values */
  summaryRow: {
    type: Object,
    default: null
  },
  /** Pagination state object { page, pageSize, total, totalPages } */
  pagination: {
    type: Object,
    default: () => ({ page: 1, pageSize: 10, total: 0, totalPages: 0 })
  },
  /** Current sort field */
  sortBy: {
    type: String,
    default: ''
  },
  /** Current sort order: 'asc' or 'desc' */
  sortOrder: {
    type: String,
    default: 'desc'
  },
  /** Whether data is loading */
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['sort', 'page-change', 'page-size-change', 'cell-click'])

/** Month header labels */
const months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

/** Sortable column definitions */
const sortableColumns = [
  { field: 'tripDays', label: '出差(天)' },
  { field: 'outingDays', label: '外出(天)' },
]

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
 * Handle clicking on a monthly data cell to open the detail modal
 */
function onCellClick(employee, monthIndex) {
  const monthStr = String(monthIndex + 1)
  const val = employee.months?.[monthStr]
  if (!isClickable(val)) return
  emit('cell-click', employee.employeeId, employee.employeeName, employee.deptName, monthIndex + 1)
}

/**
 * Get the first character of the employee name for the avatar
 */
function getInitial(name) {
  return name ? name.charAt(0) : '?'
}

/**
 * Get sort icon state for a column
 */
function getSortIcon(field) {
  if (props.sortBy === field && props.sortOrder === 'asc') return 'asc'
  if (props.sortBy === field && props.sortOrder === 'desc') return 'desc'
  return 'none'
}
</script>

<template>
  <div class="rounded-xl border-[1.5px] border-border-default overflow-hidden">
    <!-- Table info bar -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:h-12 px-4 py-2 sm:py-0 bg-white">
      <!-- Left: Record count -->
      <span class="text-xs sm:text-[13px] font-medium text-text-secondary">
        共 {{ pagination.total }} 条记录
      </span>
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
            <!-- Sortable columns: tripDays, outingDays -->
            <th
              v-for="col in sortableColumns"
              :key="col.field"
              class="px-2 py-3 text-center text-xs sm:text-[13px] font-medium text-text-secondary min-w-[64px] sm:min-w-[76px] cursor-pointer select-none hover:bg-blue-50 transition-colors"
              @click="emit('sort', col.field)"
            >
              <div class="flex items-center justify-center gap-1">
                <span>{{ col.label }}</span>
                <ArrowUp v-if="getSortIcon(col.field) === 'asc'" :size="14" />
                <ArrowDown v-else-if="getSortIcon(col.field) === 'desc'" :size="14" />
                <ArrowUpDown v-else :size="14" class="text-text-tertiary" />
              </div>
            </th>
            <!-- Monthly columns -->
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
              @click="emit('sort', 'totalDays')"
            >
              <div class="flex items-center justify-center gap-1">
                <span>合计(天)</span>
                <ArrowUp v-if="getSortIcon('totalDays') === 'asc'" :size="14" />
                <ArrowDown v-else-if="getSortIcon('totalDays') === 'desc'" :size="14" />
                <ArrowUpDown v-else :size="14" class="text-text-tertiary" />
              </div>
            </th>
          </tr>
        </thead>

        <tbody>
          <!-- Empty state -->
          <tr v-if="tableData.length === 0 && !loading">
            <td :colspan="16" class="py-16 text-center text-text-tertiary text-sm">
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
                  {{ getInitial(row.employeeName) }}
                </div>
                <span class="text-xs sm:text-sm font-medium text-text-primary truncate">{{ row.employeeName }}</span>
              </div>
            </td>
            <!-- Department column (sticky) -->
            <td class="sticky left-[70px] sm:left-[90px] z-[1] bg-white px-2 sm:px-3 py-3 text-xs sm:text-sm text-text-secondary border-r border-border-default truncate">
              {{ row.deptName }}
            </td>
            <!-- Trip days -->
            <td class="px-2 py-3 text-center text-xs sm:text-sm" :class="cellClass(row.tripDays)">
              {{ formatValue(row.tripDays) }}
            </td>
            <!-- Outing days -->
            <td class="px-2 py-3 text-center text-xs sm:text-sm" :class="cellClass(row.outingDays)">
              {{ formatValue(row.outingDays) }}
            </td>
            <!-- Monthly cells -->
            <td
              v-for="(m, mIdx) in months"
              :key="mIdx"
              class="px-2 py-3 text-center text-xs sm:text-sm transition-colors"
              :class="[
                cellClass(row.months?.[String(mIdx + 1)]),
                isClickable(row.months?.[String(mIdx + 1)]) ? 'cursor-pointer hover:bg-highlight' : ''
              ]"
              @click="onCellClick(row, mIdx)"
            >
              {{ formatValue(row.months?.[String(mIdx + 1)]) }}
            </td>
            <!-- Total column -->
            <td class="px-3 py-3 text-center text-xs sm:text-sm font-bold text-accent bg-highlight">
              {{ formatValue(row.totalDays) }}
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
            <td class="px-2 py-3 text-center text-xs sm:text-sm text-accent">
              {{ formatValue(summaryRow.tripDays) }}
            </td>
            <td class="px-2 py-3 text-center text-xs sm:text-sm text-accent">
              {{ formatValue(summaryRow.outingDays) }}
            </td>
            <td
              v-for="(m, mIdx) in months"
              :key="mIdx"
              class="px-2 py-3 text-center text-xs sm:text-sm text-accent"
            >
              {{ formatValue(summaryRow.months?.[String(mIdx + 1)]) }}
            </td>
            <td class="px-3 py-3 text-center text-xs sm:text-sm font-bold text-accent bg-blue-100">
              {{ formatValue(summaryRow.totalDays) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="border-t border-border-default bg-white">
      <Pagination
        :page="pagination.page"
        :page-size="pagination.pageSize"
        :total="pagination.total"
        @page-change="(p) => emit('page-change', p)"
        @page-size-change="(s) => emit('page-size-change', s)"
      />
    </div>
  </div>
</template>
