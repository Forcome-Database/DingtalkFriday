import { ref, reactive } from 'vue'
import api from '../api/index.js'

/**
 * Composable for managing trip (business trip / out-of-office) data query state and operations.
 * Follows the same patterns as useLeaveData.js.
 */
export function useTripData() {
  // --- Filter state ---
  const filters = reactive({
    dept1: null,          // Level 1 department ID
    dept2: null,          // Level 2 department ID
    tripType: '',         // '' = all, '出差' = business trip, '外出' = out-of-office
    year: new Date().getFullYear(),
    employeeName: '',
  })

  // --- Department options (reuse same API as leave) ---
  const departments1 = ref([])
  const departments2 = ref([])

  // --- Table data ---
  const tableData = ref([])
  const summaryRow = ref({})
  const stats = ref({
    totalCount: 0,
    totalDays: 0,
    todayTripCount: 0,
    todayOutingCount: 0,
  })

  // --- Pagination ---
  const pagination = ref({ page: 1, pageSize: 10, total: 0, totalPages: 0 })

  // --- Sorting ---
  const sortBy = ref('')
  const sortOrder = ref('desc')

  // --- Loading state ---
  const loading = ref(false)

  // --- Daily trip count state (heatmap) ---
  const dailyTripMonth = ref({
    year: new Date().getFullYear(),
    month: new Date().getMonth() + 1,
  })
  const dailyTripData = ref({ days: {} })
  const dailyTripLoading = ref(false)

  // --- Today trip detail modal state ---
  const todayTripVisible = ref(false)
  const todayTripDetail = ref([])
  const todayTripLoading = ref(false)
  const todayTripType = ref('')  // which card was clicked: '出差' or '外出' or ''
  const todayTripDate = ref(new Date().toISOString().slice(0, 10))

  // --- Calendar modal (daily detail for one employee) ---
  const calendarVisible = ref(false)
  const calendarData = ref({ employeeName: '', records: [] })
  const calendarLoading = ref(false)
  const selectedCell = ref(null)

  // --- Sync state ---
  const syncing = ref(false)

  // --- Year options (current year ±2, covering 5 years) ---
  const currentYear = new Date().getFullYear()
  const yearOptions = Array.from({ length: 5 }, (_, i) => currentYear - 2 + i)

  /**
   * Load level-1 departments
   */
  async function loadDepartments1() {
    try {
      const data = await api.getDepartments()
      departments1.value = data || []
    } catch (e) {
      console.error('Failed to load departments1', e)
      departments1.value = []
    }
  }

  /**
   * Load level-2 departments by parent ID
   */
  async function loadDepartments2(parentId) {
    if (!parentId) {
      departments2.value = []
      return
    }
    try {
      const data = await api.getDepartments(parentId)
      departments2.value = data || []
    } catch (e) {
      console.error('Failed to load departments2', e)
      departments2.value = []
    }
  }

  /**
   * Fetch monthly trip summary based on current filters
   */
  async function fetchData() {
    loading.value = true
    try {
      const deptId = filters.dept2 || filters.dept1 || undefined
      const res = await api.getTripMonthlySummary({
        year: filters.year,
        deptId,
        tripType: filters.tripType || undefined,
        employeeName: filters.employeeName || undefined,
        page: pagination.value.page,
        pageSize: pagination.value.pageSize,
        sortBy: sortBy.value || undefined,
        sortOrder: sortOrder.value,
      })
      stats.value = res.stats
      tableData.value = res.list
      summaryRow.value = res.summary
      pagination.value = res.pagination
    } catch (e) {
      console.error('Failed to fetch trip data', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch per-day trip/outing headcount for the heatmap
   */
  async function fetchDailyTripCount() {
    dailyTripLoading.value = true
    try {
      const deptId = filters.dept2 || filters.dept1 || undefined
      const res = await api.getTripDailyCount({
        year: dailyTripMonth.value.year,
        month: dailyTripMonth.value.month,
        deptId,
        tripType: filters.tripType || undefined,
        employeeName: filters.employeeName || undefined,
      })
      dailyTripData.value = res
    } catch (e) {
      console.error('Failed to fetch daily trip count', e)
    } finally {
      dailyTripLoading.value = false
    }
  }

  /**
   * Switch the daily trip count month and refresh heatmap
   */
  function setDailyTripMonth(year, month) {
    dailyTripMonth.value = { year, month }
    fetchDailyTripCount()
  }

  /**
   * Fetch daily detail for one employee (opens calendar modal)
   */
  async function fetchDailyDetail(employeeId, employeeName, dept, year, month) {
    selectedCell.value = { employeeId, employeeName, dept, year, month }
    calendarVisible.value = true
    calendarLoading.value = true
    try {
      const res = await api.getTripDailyDetail({ employeeId, year, month })
      calendarData.value = res
    } catch (e) {
      console.error('Failed to fetch trip daily detail', e)
      calendarData.value = { employeeName, records: [] }
    } finally {
      calendarLoading.value = false
    }
  }

  /**
   * Close the calendar detail modal
   */
  function closeCalendar() {
    calendarVisible.value = false
    calendarData.value = { employeeName: '', records: [] }
    selectedCell.value = null
  }

  /**
   * Fetch trip/outing detail list (opens modal, supports any date)
   * @param {string} typeOrDate - trip type ('出差'/'外出'/'') or date (YYYY-MM-DD)
   */
  async function fetchTodayTripDetail(typeOrDate = '') {
    // If it looks like a date, treat as date change keeping current type
    if (/^\d{4}-\d{2}-\d{2}$/.test(typeOrDate)) {
      todayTripDate.value = typeOrDate
    } else {
      todayTripType.value = typeOrDate
    }
    todayTripVisible.value = true
    todayTripLoading.value = true
    try {
      const deptId = filters.dept2 || filters.dept1 || undefined
      const res = await api.getTripToday({
        deptId,
        tripType: todayTripType.value || undefined,
        employeeName: filters.employeeName || undefined,
        date: todayTripDate.value,
      })
      todayTripDetail.value = res.list
    } catch (e) {
      console.error('Failed to fetch trip detail', e)
      todayTripDetail.value = []
    } finally {
      todayTripLoading.value = false
    }
  }

  /**
   * Export current trip detail as Excel
   */
  async function exportTripDetail() {
    try {
      const deptId = filters.dept2 || filters.dept1 || undefined
      const blob = await api.exportTripDetail({
        deptId,
        tripType: todayTripType.value || undefined,
        employeeName: filters.employeeName || undefined,
        date: todayTripDate.value,
      })
      const { saveAs } = await import('file-saver')
      saveAs(blob, `外出出差详情_${todayTripDate.value}.xlsx`)
    } catch (e) {
      console.error('Export trip detail failed:', e)
    }
  }

  /**
   * Close the today trip detail modal
   */
  function closeTodayTrip() {
    todayTripVisible.value = false
    todayTripDetail.value = []
    todayTripDate.value = new Date().toISOString().slice(0, 10)
  }

  /**
   * Execute search with current filters (resets to page 1)
   */
  function search() {
    pagination.value.page = 1
    fetchData()
    fetchDailyTripCount()
  }

  /**
   * Reset all filters to defaults
   */
  function resetFilters() {
    filters.dept1 = null
    filters.dept2 = null
    filters.tripType = ''
    filters.employeeName = ''
    departments2.value = []
    search()
  }

  /**
   * Navigate to a specific page
   */
  function goToPage(p) {
    pagination.value.page = p
    fetchData()
  }

  /**
   * Change page size and reset to page 1
   */
  function setPageSize(size) {
    pagination.value.pageSize = size
    pagination.value.page = 1
    fetchData()
  }

  /**
   * Toggle sort on a field; cycles desc -> asc -> desc on same field,
   * or switches to new field with 'desc'
   */
  function toggleSort(field) {
    if (sortBy.value === field) {
      sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
    } else {
      sortBy.value = field
      sortOrder.value = 'desc'
    }
    fetchData()
  }

  /**
   * Trigger trip data sync from DingTalk
   * @param {string|null} month - optional YYYY-MM to force-sync a specific month
   */
  async function triggerTripSync(month) {
    if (syncing.value) return
    syncing.value = true
    try {
      await api.triggerTripSync(month)
    } catch (e) {
      console.error('Failed to trigger trip sync', e)
    } finally {
      // Reset syncing after a short delay to indicate completion
      setTimeout(() => { syncing.value = false }, 3000)
    }
  }

  /**
   * Export trip data to Excel
   */
  async function exportTripExcel() {
    try {
      const deptId = filters.dept2 || filters.dept1 || undefined
      const blob = await api.exportTripExcel({
        year: filters.year,
        deptId,
        tripType: filters.tripType || undefined,
        employeeName: filters.employeeName || undefined,
      })
      const { saveAs } = await import('file-saver')
      saveAs(blob, `外出出差统计_${filters.year}.xlsx`)
    } catch (e) {
      console.error('Failed to export trip excel', e)
    }
  }

  return {
    // State
    filters,
    departments1,
    departments2,
    tableData,
    summaryRow,
    stats,
    pagination,
    sortBy,
    sortOrder,
    loading,
    dailyTripMonth,
    dailyTripData,
    dailyTripLoading,
    todayTripVisible,
    todayTripDetail,
    todayTripLoading,
    todayTripType,
    todayTripDate,
    calendarVisible,
    calendarData,
    calendarLoading,
    selectedCell,
    syncing,
    yearOptions,

    // Methods
    loadDepartments1,
    loadDepartments2,
    fetchData,
    fetchDailyTripCount,
    setDailyTripMonth,
    fetchDailyDetail,
    closeCalendar,
    fetchTodayTripDetail,
    exportTripDetail,
    closeTodayTrip,
    search,
    resetFilters,
    goToPage,
    setPageSize,
    toggleSort,
    triggerTripSync,
    exportTripExcel,
  }
}
