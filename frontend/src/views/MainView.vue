<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useLeaveData } from '../composables/useLeaveData.js'
import { useTripData } from '../composables/useTripData.js'
import { useAuth } from '../composables/useAuth.js'
import AppHeader from '../components/AppHeader.vue'
import FilterPanel from '../components/FilterPanel.vue'
import StatsCards from '../components/StatsCards.vue'
import DataTable from '../components/DataTable.vue'
import DailyLeaveStats from '../components/DailyLeaveStats.vue'
import LeaveCalendarModal from '../components/LeaveCalendarModal.vue'
import TodayLeaveModal from '../components/TodayLeaveModal.vue'
import TripFilterPanel from '../components/TripFilterPanel.vue'
import TripStatsCards from '../components/TripStatsCards.vue'
import TripDataTable from '../components/TripDataTable.vue'
import TripDailyStats from '../components/TripDailyStats.vue'
import TripTodayModal from '../components/TripTodayModal.vue'
import TripCalendarModal from '../components/TripCalendarModal.vue'
import AnalyticsView from '../components/AnalyticsView.vue'
import AdminPanel from '../components/AdminPanel.vue'

const router = useRouter()
const { currentUser, isAdmin, logout, refreshUser } = useAuth()

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
  todayLeaveVisible,
  todayLeaveDetail,
  todayLeaveLoading,
  todayLeaveDate,
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
  exportExcel,
  fetchTodayLeaveDetail,
  exportLeaveDetail,
  closeTodayLeave
} = useLeaveData()

const {
  filters: tripFilters,
  departments1: tripDepts1,
  departments2: tripDepts2,
  tableData: tripTableData,
  summaryRow: tripSummaryRow,
  stats: tripStats,
  pagination: tripPagination,
  sortBy: tripSortBy,
  sortOrder: tripSortOrder,
  loading: tripLoading,
  dailyTripMonth, dailyTripData, dailyTripLoading,
  todayTripVisible, todayTripDetail, todayTripLoading, todayTripType, todayTripDate,
  calendarVisible: tripCalendarVisible,
  calendarData: tripCalendarData,
  calendarLoading: tripCalendarLoading,
  selectedCell: tripSelectedCell,
  syncing: tripSyncing,
  yearOptions: tripYearOptions,
  loadDepartments1: loadTripDepts1,
  loadDepartments2: loadTripDepts2,
  fetchData: fetchTripData,
  fetchDailyTripCount, setDailyTripMonth,
  fetchDailyDetail: fetchTripDailyDetail,
  closeCalendar: closeTripCalendar,
  fetchTodayTripDetail, exportTripDetail, closeTodayTrip,
  search: tripSearch,
  resetFilters: tripResetFilters,
  goToPage: tripGoToPage,
  setPageSize: tripSetPageSize,
  toggleSort: tripToggleSort,
  triggerTripSync, exportTripExcel,
} = useTripData()

/** Active page: 'export' (default), 'trip', 'analytics', or 'admin' */
const activePage = ref('export')

/** Active tab: 'table' (default) or 'daily' */
const activeTab = ref('table')

/** Active trip tab: 'table' (default) or 'daily' */
const activeTripTab = ref('table')

/** Whether export is in progress */
const exporting = ref(false)

/** Whether trip export is in progress */
const tripExporting = ref(false)

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
 * Handle trip sync button click
 */
function handleTripSync() {
  triggerTripSync()
  // Refresh data after a delay to allow sync to process some records
  setTimeout(() => {
    fetchTripData()
    fetchDailyTripCount()
  }, 5000)
}

/**
 * Handle trip export button click
 */
async function handleTripExport() {
  tripExporting.value = true
  try {
    await exportTripExcel()
  } finally {
    tripExporting.value = false
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
  // Refresh user info from server (picks up admin status changes)
  refreshUser()
  await Promise.all([loadDepartments1(), loadLeaveTypes()])
  await fetchData()

  // Initialize trip data
  loadTripDepts1()
  fetchTripData()
  fetchDailyTripCount()
})
</script>

<template>
  <div class="min-h-screen bg-white pb-16 sm:pb-0">
    <!-- Top navigation bar -->
    <AppHeader
      :syncing="syncing"
      :exporting="exporting"
      :trip-syncing="tripSyncing"
      :trip-exporting="tripExporting"
      :sync-year="filters.year"
      :active-page="activePage"
      :current-user="currentUser"
      :is-admin="isAdmin"
      @sync="triggerSync(filters.year)"
      @export="handleExport"
      @trip-sync="handleTripSync"
      @trip-export="handleTripExport"
      @page-change="activePage = $event"
      @logout="handleLogout"
    />

    <!-- Data export page (existing content) -->
    <div v-if="activePage === 'export'" class="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6">
      <!-- Page title section -->
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-semibold text-text-primary">请假数据统计</h1>
          <p class="text-sm text-text-secondary mt-1">按部门查询和导出员工请假统计数据</p>
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
      <StatsCards
        :stats="stats"
        :unit="filters.unit"
        :today-leave-count="todayLeaveCount"
        :today-trip-count="(tripStats.todayTripCount || 0) + (tripStats.todayOutingCount || 0)"
        @today-leave-click="fetchTodayLeaveDetail"
        @today-trip-click="fetchTodayTripDetail('')"
      />

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

    <!-- Trip Page -->
    <div v-if="activePage === 'trip'" class="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6">
      <div>
        <h2 class="text-lg sm:text-xl font-bold text-text-primary">外出/出差统计</h2>
        <p class="text-[13px] text-text-secondary mt-1">查看员工出差和外出记录统计</p>
      </div>

      <TripFilterPanel
        :filters="tripFilters"
        :departments1="tripDepts1"
        :departments2="tripDepts2"
        :yearOptions="tripYearOptions"
        :loading="tripLoading"
        @update:filters="Object.assign(tripFilters, $event)"
        @dept1Change="loadTripDepts2"
        @search="tripSearch"
        @reset="tripResetFilters"
      />

      <TripStatsCards
        :stats="tripStats"
        @todayTripClick="fetchTodayTripDetail('出差')"
        @todayOutingClick="fetchTodayTripDetail('外出')"
      />

      <!-- Tab switcher -->
      <div class="flex gap-1 bg-surface-secondary rounded-lg p-1 w-fit">
        <button
          class="px-4 py-1.5 rounded-md text-[13px] font-medium transition-colors"
          :class="activeTripTab === 'table' ? 'bg-white text-accent shadow-sm' : 'text-text-secondary hover:text-text-primary'"
          @click="activeTripTab = 'table'"
        >
          出差/外出列表
        </button>
        <button
          class="px-4 py-1.5 rounded-md text-[13px] font-medium transition-colors"
          :class="activeTripTab === 'daily' ? 'bg-white text-accent shadow-sm' : 'text-text-secondary hover:text-text-primary'"
          @click="activeTripTab = 'daily'; fetchDailyTripCount()"
        >
          每日统计
        </button>
      </div>

      <TripDataTable
        v-if="activeTripTab === 'table'"
        :tableData="tripTableData"
        :summaryRow="tripSummaryRow"
        :pagination="tripPagination"
        :sortBy="tripSortBy"
        :sortOrder="tripSortOrder"
        :loading="tripLoading"
        @sort="tripToggleSort"
        @page-change="tripGoToPage"
        @page-size-change="tripSetPageSize"
        @cell-click="(empId, name, dept, month) => fetchTripDailyDetail(empId, name, dept, tripFilters.year, month)"
      />

      <TripDailyStats
        v-if="activeTripTab === 'daily'"
        :dailyData="dailyTripData"
        :month="dailyTripMonth"
        :loading="dailyTripLoading"
        @month-change="setDailyTripMonth"
      />

      <TripCalendarModal
        :visible="tripCalendarVisible"
        :data="tripCalendarData"
        :loading="tripCalendarLoading"
        :selectedCell="tripSelectedCell"
        @close="closeTripCalendar"
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

    <!-- Today leave detail modal -->
    <TodayLeaveModal
      :visible="todayLeaveVisible"
      :data="todayLeaveDetail"
      :loading="todayLeaveLoading"
      :leave-type-options="leaveTypeOptions"
      :selected-date="todayLeaveDate"
      @close="closeTodayLeave"
      @date-change="fetchTodayLeaveDetail"
      @export="exportLeaveDetail"
    />

    <!-- Today trip detail modal (page-level so it works from any page) -->
    <TripTodayModal
      :visible="todayTripVisible"
      :detail="todayTripDetail"
      :loading="todayTripLoading"
      :tripType="todayTripType"
      :selected-date="todayTripDate"
      @date-change="fetchTodayTripDetail"
      @export="exportTripDetail"
      @close="closeTodayTrip"
    />
  </div>
</template>
