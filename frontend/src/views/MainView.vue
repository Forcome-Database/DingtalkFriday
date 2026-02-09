<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useLeaveData } from '../composables/useLeaveData.js'
import { useAuth } from '../composables/useAuth.js'
import AppHeader from '../components/AppHeader.vue'
import FilterPanel from '../components/FilterPanel.vue'
import StatsCards from '../components/StatsCards.vue'
import DataTable from '../components/DataTable.vue'
import DailyLeaveStats from '../components/DailyLeaveStats.vue'
import LeaveCalendarModal from '../components/LeaveCalendarModal.vue'
import AnalyticsView from '../components/AnalyticsView.vue'
import AdminPanel from '../components/AdminPanel.vue'

const router = useRouter()
const { currentUser, isAdmin, logout } = useAuth()

const {
  // State
  filters,
  departments1,
  departments2,
  leaveTypeOptions,
  tableData,
  summaryRow,
  stats,
  pagination,
  sortBy,
  sortOrder,
  loading,
  calendarVisible,
  calendarData,
  calendarLoading,
  selectedCell,
  dailyLeaveMonth,
  dailyLeaveData,
  dailyLeaveLoading,
  todayLeaveCount,
  syncing,
  yearOptions,

  // Methods
  loadDepartments1,
  loadDepartments2,
  loadLeaveTypes,
  fetchData,
  fetchDailyLeaveCount,
  setDailyLeaveMonth,
  fetchDailyDetail,
  closeCalendar,
  search,
  resetFilters,
  goToPage,
  setPageSize,
  toggleSort,
  setUnit,
  triggerSync,
  exportExcel
} = useLeaveData()

/** Active page: 'export' (default), 'analytics', or 'admin' */
const activePage = ref('export')

/** Active tab: 'table' (default) or 'daily' */
const activeTab = ref('table')

/** Whether export is in progress */
const exporting = ref(false)

/**
 * Handle export button click
 */
async function handleExport() {
  exporting.value = true
  try {
    await exportExcel()
  } finally {
    exporting.value = false
  }
}

/**
 * Handle department level-1 selection change.
 * Loads sub-departments for the selected parent.
 */
function handleDept1Change(deptId) {
  if (deptId) {
    loadDepartments2(deptId)
  } else {
    filters.deptId2 = null
  }
}

/**
 * Handle clicking a data cell in the table.
 * Opens the calendar detail modal for that employee/month.
 */
function handleCellClick({ employeeId, name, dept, month }) {
  fetchDailyDetail(employeeId, name, dept, filters.year, month)
}

/**
 * Handle logout
 */
function handleLogout() {
  logout()
  router.push('/login')
}

// Initialize data on mount
onMounted(async () => {
  await Promise.all([loadDepartments1(), loadLeaveTypes()])
  await fetchData()
})
</script>

<template>
  <div class="min-h-screen bg-white">
    <!-- Top navigation bar -->
    <AppHeader
      :syncing="syncing"
      :exporting="exporting"
      :sync-year="filters.year"
      :active-page="activePage"
      :current-user="currentUser"
      :is-admin="isAdmin"
      @sync="triggerSync(filters.year)"
      @export="handleExport"
      @page-change="activePage = $event"
      @logout="handleLogout"
    />

    <!-- Data export page (existing content) -->
    <div v-if="activePage === 'export'" class="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6">
      <!-- Page title section -->
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-semibold text-text-primary">请假数据导出</h1>
          <p class="text-sm text-text-secondary mt-1">按部门查询和导出员工请假数据</p>
        </div>
      </div>

      <!-- Filter panel -->
      <FilterPanel
        :filters="filters"
        :departments1="departments1"
        :departments2="departments2"
        :leave-type-options="leaveTypeOptions"
        :year-options="yearOptions"
        @search="search"
        @reset="resetFilters"
        @dept1-change="handleDept1Change"
      />

      <!-- Statistics cards -->
      <StatsCards :stats="stats" :unit="filters.unit" :today-leave-count="todayLeaveCount" />

      <!-- Tab switcher -->
      <div class="flex items-center gap-1 border-b border-border-default">
        <button
          class="px-4 py-2.5 text-[13px] font-medium transition-colors relative"
          :class="activeTab === 'table'
            ? 'text-accent'
            : 'text-text-tertiary hover:text-text-secondary'"
          @click="activeTab = 'table'"
        >
          请假列表
          <span
            v-if="activeTab === 'table'"
            class="absolute bottom-0 left-0 right-0 h-[2px] bg-accent rounded-t"
          />
        </button>
        <button
          class="px-4 py-2.5 text-[13px] font-medium transition-colors relative"
          :class="activeTab === 'daily'
            ? 'text-accent'
            : 'text-text-tertiary hover:text-text-secondary'"
          @click="activeTab = 'daily'"
        >
          每日统计
          <span
            v-if="activeTab === 'daily'"
            class="absolute bottom-0 left-0 right-0 h-[2px] bg-accent rounded-t"
          />
        </button>
      </div>

      <!-- Data table with pagination (default tab) -->
      <DataTable
        v-if="activeTab === 'table'"
        :table-data="tableData"
        :summary-row="summaryRow"
        :total="pagination.total"
        :unit="filters.unit"
        :sort-by="sortBy"
        :sort-order="sortOrder"
        :page="pagination.page"
        :page-size="pagination.pageSize"
        :loading="loading"
        @unit-change="setUnit"
        @sort="toggleSort"
        @page-change="goToPage"
        @page-size-change="setPageSize"
        @cell-click="handleCellClick"
      />

      <!-- Daily leave stats (heatmap + table) -->
      <DailyLeaveStats
        v-if="activeTab === 'daily'"
        :data="dailyLeaveData"
        :month="dailyLeaveMonth"
        :year="filters.year"
        :loading="dailyLeaveLoading"
        @month-change="setDailyLeaveMonth"
      />
    </div>

    <!-- Data analytics page -->
    <AnalyticsView v-if="activePage === 'analytics'" />

    <!-- Admin panel (admin only) -->
    <AdminPanel v-if="activePage === 'admin' && isAdmin" />

    <!-- Leave calendar detail modal -->
    <LeaveCalendarModal
      :visible="calendarVisible"
      :data="calendarData"
      :loading="calendarLoading"
      :selected-cell="selectedCell"
      @close="closeCalendar"
    />
  </div>
</template>
