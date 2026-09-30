import { ref, reactive, watch, getCurrentScope, onScopeDispose } from 'vue'
import api, { waitForSyncCompletion } from '../api/index.js'
import { businessDate, businessDateParts } from '../utils/date.js'

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
    year: businessDateParts().year,
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
  const errorMessage = ref('')
  const requestVersion = { data: 0, daily: 0, detail: 0, calendar: 0, departments: 0 }

  // --- Daily trip count state (heatmap) ---
  const dailyTripMonth = ref({
    year: businessDateParts().year,
    month: businessDateParts().month,
  })
  const dailyTripData = ref({ days: {} })
  const dailyTripLoading = ref(false)

  // --- Today trip detail modal state ---
  const todayTripVisible = ref(false)
  const todayTripDetail = ref([])
  const todayTripLoading = ref(false)
  const todayTripType = ref('')  // which card was clicked: '出差' or '外出' or ''
  const todayTripDate = ref(businessDate())

  // --- Calendar modal (daily detail for one employee) ---
  const calendarVisible = ref(false)
  const calendarData = ref({ employeeName: '', records: [] })
  const calendarLoading = ref(false)
  const selectedCell = ref(null)

  // --- Sync state ---
  const syncing = ref(false)
  const syncMessage = ref('')
  const syncStatus = ref(null)
  let syncVersion = 0
  let syncController
  if (getCurrentScope()) onScopeDispose(() => { syncVersion++; syncController?.abort() })

  // --- Year options (current year ±2, covering 5 years) ---
  const currentYear = businessDateParts().year
  const yearOptions = Array.from({ length: 5 }, (_, i) => currentYear - 2 + i)

  watch(filters, () => {
    for (const key of ['data', 'daily', 'detail', 'calendar']) requestVersion[key]++
    dailyTripMonth.value = { ...dailyTripMonth.value, year: filters.year }
    loading.value = false
    dailyTripLoading.value = false
    todayTripLoading.value = false
    calendarLoading.value = false
  }, { deep: true, flush: 'sync' })

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
    const version = ++requestVersion.departments
    if (!parentId) {
      departments2.value = []
      return
    }
    try {
      const data = await api.getDepartments(parentId)
      if (version !== requestVersion.departments) return
      departments2.value = data || []
    } catch (e) {
      if (version !== requestVersion.departments) return
      console.error('Failed to load departments2', e)
      departments2.value = []
    }
  }

  /**
   * Fetch monthly trip summary based on current filters
   */
  async function fetchData() {
    const version = ++requestVersion.data
    loading.value = true
    errorMessage.value = ''
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
      if (version !== requestVersion.data) return
      stats.value = res.stats
      tableData.value = res.list
      summaryRow.value = res.summary
      pagination.value = res.pagination
    } catch (e) {
      if (version !== requestVersion.data) return
      console.error('Failed to fetch trip data', e)
      errorMessage.value = '外出/出差数据加载失败，请重试'
      tableData.value = []
      summaryRow.value = {}
      stats.value = { totalCount: 0, totalDays: 0, todayTripCount: 0, todayOutingCount: 0 }
    } finally {
      if (version === requestVersion.data) loading.value = false
    }
  }

  /**
   * Fetch per-day trip/outing headcount for the heatmap
   */
  async function fetchDailyTripCount() {
    const version = ++requestVersion.daily
    dailyTripLoading.value = true
    try {
      const deptId = filters.dept2 || filters.dept1 || undefined
      const res = await api.getTripDailyCount({
        year: filters.year,
        month: dailyTripMonth.value.month,
        deptId,
        tripType: filters.tripType || undefined,
        employeeName: filters.employeeName || undefined,
      })
      if (version !== requestVersion.daily) return
      dailyTripData.value = res
    } catch (e) {
      if (version !== requestVersion.daily) return
      console.error('Failed to fetch daily trip count', e)
    } finally {
      if (version === requestVersion.daily) dailyTripLoading.value = false
    }
  }

  /**
   * Switch the daily trip count month and refresh heatmap
   */
  function setDailyTripMonth(year, month) {
    filters.year = year
    dailyTripMonth.value = { year, month }
    fetchDailyTripCount()
  }

  /**
   * Fetch daily detail for one employee (opens calendar modal)
   */
  async function fetchDailyDetail(employeeId, employeeName, dept, year, month) {
    const version = ++requestVersion.calendar
    selectedCell.value = { employeeId, employeeName, dept, year, month }
    calendarVisible.value = true
    calendarLoading.value = true
    try {
      const res = await api.getTripDailyDetail({ employeeId, year, month, tripType: filters.tripType })
      if (version !== requestVersion.calendar) return
      calendarData.value = res
    } catch (e) {
      if (version !== requestVersion.calendar) return
      console.error('Failed to fetch trip daily detail', e)
      calendarData.value = { employeeName, records: [] }
    } finally {
      if (version === requestVersion.calendar) calendarLoading.value = false
    }
  }

  /**
   * Close the calendar detail modal
   */
  function closeCalendar() {
    requestVersion.calendar++
    calendarLoading.value = false
    calendarVisible.value = false
    calendarData.value = { employeeName: '', records: [] }
    selectedCell.value = null
  }

  /**
   * Fetch trip/outing detail list (opens modal, supports any date)
   * @param {string} typeOrDate - trip type ('出差'/'外出'/'') or date (YYYY-MM-DD)
   */
  async function fetchTodayTripDetail(typeOrDate = '') {
    const version = ++requestVersion.detail
    // If it looks like a date, treat as date change keeping current type
    if (/^\d{4}-\d{2}-\d{2}$/.test(typeOrDate)) {
      todayTripDate.value = typeOrDate
    } else {
      todayTripType.value = typeOrDate
      todayTripDate.value = businessDate()
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
      if (version !== requestVersion.detail) return
      todayTripDetail.value = res.list
    } catch (e) {
      if (version !== requestVersion.detail) return
      console.error('Failed to fetch trip detail', e)
      todayTripDetail.value = []
    } finally {
      if (version === requestVersion.detail) todayTripLoading.value = false
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
    requestVersion.detail++
    todayTripLoading.value = false
    todayTripVisible.value = false
    todayTripDetail.value = []
    todayTripDate.value = businessDate()
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
  function applySyncStatus(status) {
    syncStatus.value = status
  }

  function beginSyncObservation() {
    syncController?.abort()
    syncController = new AbortController()
    const version = ++syncVersion
    return {
      version, signal: syncController.signal,
      onStatus: status => { if (version === syncVersion) applySyncStatus(status) }
    }
  }

  async function refreshSyncStatus() {
    if (syncing.value) return
    const { version, signal, onStatus } = beginSyncObservation()
    try {
      const status = await api.getSyncStatus(signal)
      if (version !== syncVersion) return
      applySyncStatus(status)
      syncing.value = Boolean(status.running?.trip)
      if (status.running?.trip) {
        const latest = await waitForSyncCompletion('trip', null, onStatus, signal)
        if (version !== syncVersion) return
        syncMessage.value = latest.status === 'success' ? '同步完成' : `同步${latest.status === 'partial' ? '部分完成' : '失败'}: ${latest.message || ''}`
        await Promise.all([fetchData(), fetchDailyTripCount()])
      }
    } catch (e) {
      if (version !== syncVersion) return
      syncMessage.value = '同步状态查询失败，任务状态未知，请刷新重试'
    } finally {
      if (version === syncVersion) syncing.value = false
    }
  }

  async function triggerTripSync(month) {
    if (syncing.value) return false
    const { version, signal, onStatus } = beginSyncObservation()
    syncing.value = true
    syncMessage.value = ''
    try {
      const before = await api.getSyncStatus(signal)
      if (version !== syncVersion) return false
      syncStatus.value = before
      let latest
      if (before.running?.trip) {
        syncMessage.value = '后台正在同步，请稍候'
        latest = await waitForSyncCompletion('trip', null, onStatus, signal)
      } else {
        const result = await api.triggerTripSync(month)
        if (version !== syncVersion) return false
        if (result.success === false) {
          syncMessage.value = result.message || '同步未启动'
          return false
        }
        syncMessage.value = '同步中...'
        latest = await waitForSyncCompletion('trip', before.latest?.trip?.id || 0, onStatus, signal)
      }
      if (version !== syncVersion) return false
      syncMessage.value = latest.status === 'success' ? '同步完成' : `同步${latest.status === 'partial' ? '部分完成' : '失败'}: ${latest.message || ''}`
      await Promise.all([fetchData(), fetchDailyTripCount()])
      return latest.status === 'success'
    } catch (e) {
      if (version !== syncVersion) return false
      console.error('Failed to trigger trip sync', e)
      syncMessage.value = '同步请求或状态查询失败，任务状态未知，请刷新重试'
      return false
    } finally {
      if (version === syncVersion) syncing.value = false
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
    syncMessage,
    syncStatus,
    errorMessage,
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
    refreshSyncStatus,
    exportTripExcel,
  }
}
