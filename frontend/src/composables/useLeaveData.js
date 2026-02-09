import { ref, reactive, computed, watch } from 'vue'
import api from '../api/index.js'

/**
 * Mock data generator for development when backend is not available.
 * Returns realistic-looking leave data so the UI is fully functional.
 */
function generateMockData(filters, page, pageSize) {
  const employees = [
    { employeeId: 'U001', name: '张三', dept: '研发部', avatar: '' },
    { employeeId: 'U002', name: '李四', dept: '研发部', avatar: '' },
    { employeeId: 'U003', name: '王五', dept: '产品部', avatar: '' },
    { employeeId: 'U004', name: '赵六', dept: '设计部', avatar: '' },
    { employeeId: 'U005', name: '孙七', dept: '测试部', avatar: '' },
    { employeeId: 'U006', name: '周八', dept: '运维部', avatar: '' },
    { employeeId: 'U007', name: '吴九', dept: '研发部', avatar: '' },
    { employeeId: 'U008', name: '郑十', dept: '产品部', avatar: '' },
    { employeeId: 'U009', name: '陈明', dept: '研发部', avatar: '' },
    { employeeId: 'U010', name: '林芳', dept: '设计部', avatar: '' },
    { employeeId: 'U011', name: '黄强', dept: '测试部', avatar: '' },
    { employeeId: 'U012', name: '刘洋', dept: '运维部', avatar: '' }
  ]

  // Filter by employee name if provided
  let filtered = employees
  if (filters.employeeName) {
    filtered = employees.filter(e => e.name.includes(filters.employeeName))
  }

  const total = filtered.length
  const startIdx = (page - 1) * pageSize
  const pageItems = filtered.slice(startIdx, startIdx + pageSize)

  const isDayUnit = filters.unit === 'day'
  const multiplier = isDayUnit ? 1 : 8

  // Generate random monthly values for each employee
  const list = pageItems.map(emp => {
    const months = Array.from({ length: 12 }, () => {
      const hasLeave = Math.random() > 0.6
      if (!hasLeave) return 0
      const days = Math.round((Math.random() * 3 + 0.5) * 10) / 10
      return isDayUnit ? days : Math.round(days * 8 * 10) / 10
    })
    const empTotal = Math.round(months.reduce((a, b) => a + b, 0) * 10) / 10
    return { ...emp, months, total: empTotal }
  })

  // Compute summary row
  const summaryMonths = Array.from({ length: 12 }, (_, i) =>
    Math.round(list.reduce((sum, emp) => sum + emp.months[i], 0) * 10) / 10
  )
  const summaryTotal = Math.round(summaryMonths.reduce((a, b) => a + b, 0) * 10) / 10

  const totalDays = isDayUnit
    ? list.reduce((s, e) => s + e.total, 0)
    : Math.round(list.reduce((s, e) => s + e.total, 0) / 8 * 10) / 10
  const uniqueEmployees = list.length || 1

  return {
    stats: {
      totalCount: Math.floor(Math.random() * 20) + 20,
      totalDays: Math.round(totalDays * 10) / 10,
      avgDays: Math.round((totalDays / uniqueEmployees) * 10) / 10,
      annualRatio: 47,
      annualDays: Math.round(totalDays * 0.47 * 10) / 10
    },
    list,
    summary: {
      personCount: total,
      months: summaryMonths,
      total: summaryTotal
    },
    pagination: {
      page,
      pageSize,
      total
    }
  }
}

/**
 * Generate mock daily detail data for a specific employee/month
 */
function generateMockDailyDetail(employeeId, year, month) {
  const names = {
    'U001': '张三', 'U002': '李四', 'U003': '王五', 'U004': '赵六',
    'U005': '孙七', 'U006': '周八', 'U007': '吴九', 'U008': '郑十',
    'U009': '陈明', 'U010': '林芳', 'U011': '黄强', 'U012': '刘洋'
  }
  const depts = {
    'U001': '研发部', 'U002': '研发部', 'U003': '产品部', 'U004': '设计部',
    'U005': '测试部', 'U006': '运维部', 'U007': '研发部', 'U008': '产品部',
    'U009': '研发部', 'U010': '设计部', 'U011': '测试部', 'U012': '运维部'
  }
  const leaveTypes = ['年假', '事假', '病假', '调休']
  const statuses = ['已审批', '已审批', '已审批', '审批中']

  // Generate 2-4 random leave records for the month
  const recordCount = Math.floor(Math.random() * 3) + 2
  const records = []
  const daysInMonth = new Date(year, month, 0).getDate()

  const usedDays = new Set()
  for (let i = 0; i < recordCount; i++) {
    let day
    do {
      day = Math.floor(Math.random() * daysInMonth) + 1
    } while (usedDays.has(day))
    usedDays.add(day)

    const isFullDay = Math.random() > 0.4
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    const hours = isFullDay ? 8 : 4
    const startTime = isFullDay ? '09:00' : '14:00'
    const endTime = isFullDay ? '18:00' : '18:00'

    records.push({
      date: dateStr,
      startTime,
      endTime,
      hours,
      leaveType: leaveTypes[Math.floor(Math.random() * leaveTypes.length)],
      status: statuses[Math.floor(Math.random() * statuses.length)]
    })
  }

  records.sort((a, b) => a.date.localeCompare(b.date))

  const totalHours = records.reduce((s, r) => s + r.hours, 0)

  return {
    employee: {
      name: names[employeeId] || '未知',
      dept: depts[employeeId] || '未知部门',
      avatar: ''
    },
    records,
    summary: {
      totalDays: Math.round(totalHours / 8 * 10) / 10,
      totalHours
    }
  }
}

/**
 * Generate mock department data
 */
function generateMockDepartments(parentId) {
  if (parentId === 1) {
    return [
      { dept_id: 1, name: '全部部门', parent_id: null, hasChildren: false },
      { dept_id: 100, name: '技术中心', parent_id: 1, hasChildren: true },
      { dept_id: 200, name: '产品中心', parent_id: 1, hasChildren: true },
      { dept_id: 300, name: '运营中心', parent_id: 1, hasChildren: true }
    ]
  }
  if (parentId === 100) {
    return [
      { dept_id: 101, name: '研发部', parent_id: 100, hasChildren: false },
      { dept_id: 102, name: '测试部', parent_id: 100, hasChildren: false },
      { dept_id: 103, name: '运维部', parent_id: 100, hasChildren: false }
    ]
  }
  if (parentId === 200) {
    return [
      { dept_id: 201, name: '产品部', parent_id: 200, hasChildren: false },
      { dept_id: 202, name: '设计部', parent_id: 200, hasChildren: false }
    ]
  }
  if (parentId === 300) {
    return [
      { dept_id: 301, name: '市场部', parent_id: 300, hasChildren: false },
      { dept_id: 302, name: '销售部', parent_id: 300, hasChildren: false }
    ]
  }
  return []
}

// Flag to determine if we should use mock data (when API is unavailable)
const USE_MOCK = false

/**
 * Composable for managing leave data query state and operations.
 * Encapsulates all filter state, table data, statistics, pagination, and methods.
 */
export function useLeaveData() {
  // --- Filter state ---
  const currentYear = new Date().getFullYear()
  const filters = reactive({
    year: currentYear,
    deptId: null,       // Level 1 department ID
    deptId2: null,      // Level 2 department ID
    leaveTypes: [],     // Selected leave types (populated after loading from API)
    employeeName: '',
    unit: 'hour'        // 'day' or 'hour'
  })

  // --- Department data ---
  const departments1 = ref([])   // Level 1 departments
  const departments2 = ref([])   // Level 2 departments
  const deptsLoading = ref(false)

  // --- Leave type options (dynamic from API) ---
  const leaveTypeOptions = ref([])

  // --- Table data ---
  const tableData = ref([])
  const summaryRow = ref(null)
  const stats = ref({
    totalCount: 0,
    totalDays: 0,
    avgDays: 0,
    annualRatio: 0,
    annualDays: 0
  })

  // --- Pagination ---
  const pagination = reactive({
    page: 1,
    pageSize: 10,
    total: 0
  })

  // --- Sorting ---
  const sortBy = ref('name')
  const sortOrder = ref('')  // '', 'asc', 'desc'

  // --- Loading state ---
  const loading = ref(false)

  // --- Calendar modal state ---
  const calendarVisible = ref(false)
  const calendarData = ref(null)
  const calendarLoading = ref(false)
  const selectedCell = reactive({
    employeeId: '',
    employeeName: '',
    dept: '',
    year: currentYear,
    month: 1
  })

  // --- Daily leave count state ---
  const dailyLeaveMonth = ref(new Date().getMonth() + 1)
  const dailyLeaveData = ref(null)
  const dailyLeaveLoading = ref(false)
  const todayLeaveCount = ref(0)

  // --- Sync state ---
  const syncing = ref(false)
  const syncMessage = ref('')

  // --- Year options (recent 5 years) ---
  const yearOptions = computed(() => {
    const years = []
    for (let y = currentYear; y >= currentYear - 4; y--) {
      years.push(y)
    }
    return years
  })

  /**
   * Load level-1 departments
   */
  async function loadDepartments1() {
    deptsLoading.value = true
    try {
      if (USE_MOCK) {
        departments1.value = generateMockDepartments(1)
      } else {
        const data = await api.getDepartments()
        departments1.value = data
      }
    } catch (e) {
      console.error('Failed to load departments:', e)
      departments1.value = generateMockDepartments(1)
    } finally {
      deptsLoading.value = false
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
    deptsLoading.value = true
    try {
      if (USE_MOCK) {
        departments2.value = generateMockDepartments(parentId)
      } else {
        const data = await api.getDepartments(parentId)
        departments2.value = data
      }
    } catch (e) {
      console.error('Failed to load sub-departments:', e)
      departments2.value = generateMockDepartments(parentId)
    } finally {
      deptsLoading.value = false
    }
  }

  // Color schemes for dynamic leave types
  const knownTypeColors = {
    '年假': { bgColor: 'bg-leave-annual-bg', textColor: 'text-leave-annual-text', borderColor: 'border-[#93C5FD]' },
    '事假': { bgColor: 'bg-leave-personal-bg', textColor: 'text-leave-personal-text', borderColor: 'border-[#FCD34D]' },
    '病假': { bgColor: 'bg-leave-sick-bg', textColor: 'text-leave-sick-text', borderColor: 'border-[#FCA5A5]' },
    '调休': { bgColor: 'bg-leave-comp-bg', textColor: 'text-leave-comp-text', borderColor: 'border-[#6EE7B7]' }
  }
  const colorPool = [
    { bgColor: 'bg-purple-100', textColor: 'text-purple-700', borderColor: 'border-purple-300' },
    { bgColor: 'bg-orange-100', textColor: 'text-orange-700', borderColor: 'border-orange-300' },
    { bgColor: 'bg-teal-100', textColor: 'text-teal-700', borderColor: 'border-teal-300' },
    { bgColor: 'bg-pink-100', textColor: 'text-pink-700', borderColor: 'border-pink-300' },
    { bgColor: 'bg-indigo-100', textColor: 'text-indigo-700', borderColor: 'border-indigo-300' },
    { bgColor: 'bg-cyan-100', textColor: 'text-cyan-700', borderColor: 'border-cyan-300' }
  ]

  /**
   * Load leave types from API and set default filters
   */
  async function loadLeaveTypes() {
    try {
      if (USE_MOCK) {
        leaveTypeOptions.value = [
          { name: '年假', ...knownTypeColors['年假'] },
          { name: '事假', ...knownTypeColors['事假'] },
          { name: '病假', ...knownTypeColors['病假'] },
          { name: '调休', ...knownTypeColors['调休'] }
        ]
      } else {
        const types = await api.getLeaveTypes()
        let poolIdx = 0
        leaveTypeOptions.value = types.map(t => {
          const colors = knownTypeColors[t.leave_name]
          if (colors) {
            return { name: t.leave_name, ...colors }
          }
          const poolColor = colorPool[poolIdx % colorPool.length]
          poolIdx++
          return { name: t.leave_name, ...poolColor }
        })
      }
      // Default: select all leave types
      filters.leaveTypes = leaveTypeOptions.value.map(t => t.name)
    } catch (e) {
      console.error('Failed to load leave types:', e)
      // Fallback to known types
      leaveTypeOptions.value = [
        { name: '年假', ...knownTypeColors['年假'] },
        { name: '事假', ...knownTypeColors['事假'] },
        { name: '病假', ...knownTypeColors['病假'] },
        { name: '调休', ...knownTypeColors['调休'] }
      ]
      filters.leaveTypes = leaveTypeOptions.value.map(t => t.name)
    }
  }

  /**
   * Fetch monthly summary data based on current filters
   */
  async function fetchData() {
    loading.value = true
    try {
      const effectiveDeptId = filters.deptId2 || filters.deptId
      const params = {
        year: filters.year,
        deptId: effectiveDeptId,
        leaveTypes: filters.leaveTypes,
        employeeName: filters.employeeName,
        unit: filters.unit,
        page: pagination.page,
        pageSize: pagination.pageSize,
        sortBy: sortBy.value,
        sortOrder: sortOrder.value || undefined
      }

      let data
      if (USE_MOCK) {
        // Simulate network delay
        await new Promise(resolve => setTimeout(resolve, 300))
        data = generateMockData(params, pagination.page, pagination.pageSize)
      } else {
        data = await api.getMonthlySummary(params)
      }

      stats.value = data.stats
      tableData.value = data.list
      summaryRow.value = data.summary
      pagination.total = data.pagination.total
    } catch (e) {
      console.error('Failed to fetch leave data:', e)
      // Fallback to mock data on error
      const mockData = generateMockData(
        { ...filters, page: pagination.page, pageSize: pagination.pageSize },
        pagination.page,
        pagination.pageSize
      )
      stats.value = mockData.stats
      tableData.value = mockData.list
      summaryRow.value = mockData.summary
      pagination.total = mockData.pagination.total
    } finally {
      loading.value = false
    }

    // Also refresh daily leave count + today count
    fetchDailyLeaveCount()
    fetchTodayLeaveCount()
  }

  /**
   * Fetch daily leave count (per-day headcount) for the selected month
   */
  async function fetchDailyLeaveCount() {
    dailyLeaveLoading.value = true
    try {
      const effectiveDeptId = filters.deptId2 || filters.deptId
      const params = {
        year: filters.year,
        month: dailyLeaveMonth.value,
        deptId: effectiveDeptId,
        leaveTypes: filters.leaveTypes,
        employeeName: filters.employeeName
      }

      if (USE_MOCK) {
        await new Promise(resolve => setTimeout(resolve, 200))
        // Generate mock daily leave count data
        const daysInMonth = new Date(filters.year, dailyLeaveMonth.value, 0).getDate()
        const mockDays = []
        let maxCount = 0
        for (let d = 1; d <= daysInMonth; d++) {
          const date = `${filters.year}-${String(dailyLeaveMonth.value).padStart(2, '0')}-${String(d).padStart(2, '0')}`
          const count = Math.random() > 0.5 ? Math.floor(Math.random() * 6) : 0
          if (count > maxCount) maxCount = count
          const employees = Array.from({ length: count }, (_, i) => ({
            name: ['张三', '李四', '王五', '赵六', '孙七', '周八'][i % 6],
            dept: ['研发部', '产品部', '设计部'][i % 3],
            leaveType: ['年假', '事假', '病假', '调休'][i % 4]
          }))
          mockDays.push({ date, count, employees })
        }
        const today = new Date()
        const todayCount = (today.getFullYear() === filters.year && today.getMonth() + 1 === dailyLeaveMonth.value)
          ? (mockDays[today.getDate() - 1]?.count || 0)
          : 0
        dailyLeaveData.value = { todayCount, days: mockDays, maxCount }
      } else {
        dailyLeaveData.value = await api.getDailyLeaveCount(params)
      }
    } catch (e) {
      console.error('Failed to fetch daily leave count:', e)
      dailyLeaveData.value = null
    } finally {
      dailyLeaveLoading.value = false
    }
  }

  /**
   * Switch the daily leave count month and refresh
   */
  function setDailyLeaveMonth(month) {
    dailyLeaveMonth.value = month
    fetchDailyLeaveCount()
  }

  /**
   * Fetch today's leave count independently (always uses current date, not affected by month selector)
   */
  async function fetchTodayLeaveCount() {
    const now = new Date()
    const todayYear = now.getFullYear()
    const todayMonth = now.getMonth() + 1
    try {
      const effectiveDeptId = filters.deptId2 || filters.deptId
      const params = {
        year: todayYear,
        month: todayMonth,
        deptId: effectiveDeptId,
        leaveTypes: filters.leaveTypes,
        employeeName: filters.employeeName
      }
      if (USE_MOCK) {
        todayLeaveCount.value = Math.floor(Math.random() * 10)
      } else {
        const result = await api.getDailyLeaveCount(params)
        todayLeaveCount.value = result.todayCount ?? 0
      }
    } catch (e) {
      console.error('Failed to fetch today leave count:', e)
    }
  }

  /**
   * Fetch daily detail for the calendar modal
   */
  async function fetchDailyDetail(employeeId, name, dept, year, month) {
    calendarLoading.value = true
    calendarVisible.value = true
    selectedCell.employeeId = employeeId
    selectedCell.employeeName = name
    selectedCell.dept = dept
    selectedCell.year = year
    selectedCell.month = month

    try {
      let data
      if (USE_MOCK) {
        await new Promise(resolve => setTimeout(resolve, 200))
        data = generateMockDailyDetail(employeeId, year, month)
      } else {
        data = await api.getDailyDetail(employeeId, year, month)
      }
      calendarData.value = data
    } catch (e) {
      console.error('Failed to fetch daily detail:', e)
      calendarData.value = generateMockDailyDetail(employeeId, year, month)
    } finally {
      calendarLoading.value = false
    }
  }

  /**
   * Close the calendar modal
   */
  function closeCalendar() {
    calendarVisible.value = false
    calendarData.value = null
  }

  /**
   * Execute search with current filters (resets to page 1)
   */
  function search() {
    pagination.page = 1
    fetchData()
  }

  /**
   * Reset all filters to defaults
   */
  function resetFilters() {
    filters.year = currentYear
    filters.deptId = null
    filters.deptId2 = null
    filters.leaveTypes = leaveTypeOptions.value.map(t => t.name)
    filters.employeeName = ''
    filters.unit = 'hour'
    sortBy.value = 'name'
    sortOrder.value = ''
    pagination.page = 1
    departments2.value = []
    fetchData()
  }

  /**
   * Change page size and reset to page 1
   */
  function setPageSize(size) {
    pagination.pageSize = size
    pagination.page = 1
    fetchData()
  }

  /**
   * Navigate to a specific page
   */
  function goToPage(page) {
    pagination.page = page
    fetchData()
  }

  /**
   * Toggle sort on the total column
   * Cycles through: none -> asc -> desc -> none
   */
  function toggleSort() {
    if (sortOrder.value === '') {
      sortBy.value = 'total'
      sortOrder.value = 'asc'
    } else if (sortOrder.value === 'asc') {
      sortOrder.value = 'desc'
    } else {
      sortBy.value = 'name'
      sortOrder.value = ''
    }
    pagination.page = 1
    fetchData()
  }

  /**
   * Switch the display unit (day / hour)
   */
  function setUnit(unit) {
    filters.unit = unit
    fetchData()
  }

  /**
   * Trigger data sync from DingTalk
   */
  async function triggerSync(year) {
    if (syncing.value) return
    syncing.value = true
    syncMessage.value = ''

    try {
      if (USE_MOCK) {
        await new Promise(resolve => setTimeout(resolve, 2000))
        syncMessage.value = '同步完成'
      } else {
        await api.triggerSync(year)
        // Poll sync status - response is { logs: [...] }
        let attempts = 0
        const maxAttempts = 60
        while (attempts < maxAttempts) {
          await new Promise(resolve => setTimeout(resolve, 2000))
          const result = await api.getSyncStatus()
          const logs = result.logs || []
          // Find the most recent "full" sync log entry
          const latest = logs.find(log => log.sync_type === 'full') || logs[0]
          if (latest && latest.status === 'success') {
            syncMessage.value = '同步完成'
            break
          } else if (latest && latest.status === 'failed') {
            syncMessage.value = '同步失败: ' + (latest.message || '')
            break
          }
          attempts++
        }
      }
      // Refresh data after sync
      fetchData()
    } catch (e) {
      console.error('Sync failed:', e)
      syncMessage.value = '同步请求失败'
    } finally {
      syncing.value = false
    }
  }

  /**
   * Export data to Excel
   */
  async function exportExcel() {
    try {
      const effectiveDeptId = filters.deptId2 || filters.deptId
      const params = {
        year: filters.year,
        deptId: effectiveDeptId,
        leaveTypes: filters.leaveTypes,
        employeeName: filters.employeeName,
        unit: filters.unit
      }

      if (USE_MOCK) {
        // Create a simple mock download
        await new Promise(resolve => setTimeout(resolve, 500))
        alert('Mock: Excel 导出成功（开发模式）')
        return
      }

      const blob = await api.exportExcel(params)
      // Use file-saver to download the blob
      const { saveAs } = await import('file-saver')
      const deptName = departments1.value.find(d => d.dept_id === effectiveDeptId)?.name || '全部'
      const fileName = `请假数据_${deptName}_${filters.year}.xlsx`
      saveAs(blob, fileName)
    } catch (e) {
      console.error('Export failed:', e)
      alert('导出失败，请稍后再试')
    }
  }

  return {
    // State
    filters,
    departments1,
    departments2,
    deptsLoading,
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
    syncMessage,
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
  }
}
