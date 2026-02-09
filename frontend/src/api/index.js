import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000
})

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.detail || error.message || '请求失败'
    console.error('[API Error]', message)
    return Promise.reject(error)
  }
)

export default {
  /**
   * Get department list by parent ID
   * @param {number} parentId - Parent department ID, defaults to 1 (root)
   * @returns {Promise<Array<{dept_id: number, name: string, parent_id: number, hasChildren: boolean}>>}
   */
  getDepartments(parentId) {
    return api.get('/departments', { params: { parentId: parentId || undefined } })
  },

  /**
   * Get available leave types
   * @returns {Promise<Array<{leave_code: string, leave_name: string}>>}
   */
  getLeaveTypes() {
    return api.get('/leave/types')
  },

  /**
   * Get monthly leave summary data
   * @param {Object} params - Query parameters
   * @param {number} params.year - Year
   * @param {number} [params.deptId] - Department ID
   * @param {string[]} [params.leaveTypes] - Leave type names array
   * @param {string} [params.employeeName] - Employee name keyword
   * @param {string} params.unit - Unit: 'day' or 'hour'
   * @param {number} params.page - Page number
   * @param {number} params.pageSize - Items per page
   * @param {string} [params.sortBy] - Sort field
   * @param {string} [params.sortOrder] - Sort order: 'asc' or 'desc'
   * @returns {Promise<{stats: Object, list: Array, summary: Object, pagination: Object}>}
   */
  getMonthlySummary(params) {
    return api.get('/leave/monthly-summary', {
      params: {
        year: params.year,
        deptId: params.deptId || undefined,
        leaveTypes: params.leaveTypes?.length ? params.leaveTypes.join(',') : undefined,
        employeeName: params.employeeName || undefined,
        unit: params.unit,
        page: params.page,
        pageSize: params.pageSize,
        sortBy: params.sortBy || undefined,
        sortOrder: params.sortOrder || undefined
      }
    })
  },

  /**
   * Get daily leave detail for an employee in a specific month
   * @param {string} employeeId - Employee user ID
   * @param {number} year - Year
   * @param {number} month - Month (1-12)
   * @returns {Promise<{employee: Object, records: Array, summary: Object}>}
   */
  getDailyDetail(employeeId, year, month) {
    return api.get('/leave/daily-detail', {
      params: { employeeId, year, month }
    })
  },

  /**
   * Get per-day leave headcount for a given month
   * @param {Object} params - Query parameters
   * @param {number} params.year - Year
   * @param {number} params.month - Month (1-12)
   * @param {number} [params.deptId] - Department ID
   * @param {string[]} [params.leaveTypes] - Leave type names array
   * @param {string} [params.employeeName] - Employee name keyword
   * @returns {Promise<{todayCount: number, days: Array, maxCount: number}>}
   */
  getDailyLeaveCount(params) {
    return api.get('/leave/daily-leave-count', {
      params: {
        year: params.year,
        month: params.month,
        deptId: params.deptId || undefined,
        leaveTypes: params.leaveTypes?.length ? params.leaveTypes.join(',') : undefined,
        employeeName: params.employeeName || undefined
      }
    })
  },

  /**
   * Export leave data as Excel file
   * @param {Object} params - Export parameters
   * @param {number} params.year - Year
   * @param {number} [params.deptId] - Department ID
   * @param {string[]} [params.leaveTypes] - Leave type names
   * @param {string} [params.employeeName] - Employee name keyword
   * @param {string} params.unit - Unit: 'day' or 'hour'
   * @returns {Promise<Blob>} Excel file blob
   */
  exportExcel(params) {
    return api.post('/leave/export', {
      year: params.year,
      deptId: params.deptId || undefined,
      leaveTypes: params.leaveTypes?.length ? params.leaveTypes : undefined,
      employeeName: params.employeeName || undefined,
      unit: params.unit
    }, {
      responseType: 'blob'
    })
  },

  /**
   * Trigger data sync from DingTalk
   * @param {number} [year] - Year to sync, defaults to current year on server
   * @returns {Promise<{message: string, sync_id: number}>}
   */
  triggerSync(year) {
    return api.post('/sync', { year })
  },

  /**
   * Query current sync status
   * @returns {Promise<{status: string, message: string, started_at: string, finished_at: string}>}
   */
  getSyncStatus() {
    return api.get('/sync/status')
  },

  // --- Analytics API ---

  /**
   * Get monthly leave trend data for a given year
   * @param {number} year - Year
   * @returns {Promise<{current: number[], previous: number[]}>}
   */
  getMonthlyTrend(year) {
    return api.get('/analytics/monthly-trend', { params: { year } })
  },

  /**
   * Get leave type distribution for a given year
   * @param {number} year - Year
   * @returns {Promise<Array<{type: string, days: number, ratio: number}>>}
   */
  getLeaveTypeDistribution(year) {
    return api.get('/analytics/leave-type-distribution', { params: { year } })
  },

  /**
   * Get department comparison data for a given year
   * @param {number} year - Year
   * @param {string} [metric='total'] - Metric: 'total' or 'avg'
   * @returns {Promise<Array<{dept: string, value: number}>>}
   */
  getDepartmentComparison(year, metric = 'total') {
    return api.get('/analytics/department-comparison', { params: { year, metric } })
  },

  /**
   * Get weekday distribution data for a given year
   * @param {number} year - Year
   * @returns {Promise<Array<{weekday: string, days: number}>>}
   */
  getWeekdayDistribution(year) {
    return api.get('/analytics/weekday-distribution', { params: { year } })
  },

  /**
   * Get employee leave ranking for a given year
   * @param {number} year - Year
   * @param {number} [limit=10] - Number of top employees to return
   * @returns {Promise<Array<{name: string, dept: string, details: Object, total: number}>>}
   */
  getEmployeeRanking(year, limit = 10) {
    return api.get('/analytics/employee-ranking', { params: { year, limit } })
  }
}
