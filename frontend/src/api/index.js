import axios from 'axios'
import { getToken, removeToken, removeUser } from '../utils/auth.js'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000
})

// Request interceptor: attach JWT token
api.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status
    if (status === 401) {
      // Token expired or invalid, clear auth state and redirect
      removeToken()
      removeUser()
      // Use location to force full page reload to login
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    const message = error.response?.data?.detail || error.message || '请求失败'
    console.error('[API Error]', message)
    return Promise.reject(error)
  }
)

export default {
  // --- Auth API ---

  /**
   * Get DingTalk config (corpId)
   */
  getAuthConfig() {
    return api.get('/auth/config')
  },

  /**
   * DingTalk H5 login
   * @param {{ authCode: string }} data
   */
  loginDingTalk(data) {
    return api.post('/auth/dingtalk', data)
  },

  /**
   * Dev mode login by phone number (only when DEV_MODE=true)
   * @param {{ mobile: string }} data
   */
  devLogin(data) {
    return api.post('/auth/dev-login', data)
  },

  /**
   * Get current user info
   */
  getMe() {
    return api.get('/auth/me')
  },

  // --- Admin API ---

  /**
   * List all allowed users (admin only)
   */
  getUsers() {
    return api.get('/admin/users')
  },

  /**
   * Add an allowed user (admin only)
   * @param {{ mobile: string, name?: string }} data
   */
  addUser(data) {
    return api.post('/admin/users', data)
  },

  /**
   * Remove an allowed user (admin only)
   * @param {string} mobile
   */
  removeUser(mobile) {
    return api.delete(`/admin/users/${mobile}`)
  },

  // --- Existing API (unchanged) ---

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
   */
  getDailyDetail(employeeId, year, month) {
    return api.get('/leave/daily-detail', {
      params: { employeeId, year, month }
    })
  },

  /**
   * Get per-day leave headcount for a given month
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
   * Get today's leave detail (list of employees on leave with time info)
   */
  getTodayLeaveDetail(params) {
    return api.get('/leave/today-detail', {
      params: {
        deptId: params.deptId || undefined,
        leaveTypes: params.leaveTypes?.length ? params.leaveTypes.join(',') : undefined,
        employeeName: params.employeeName || undefined
      }
    })
  },

  /**
   * Export leave data as Excel file
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
   */
  triggerSync(year) {
    return api.post('/sync', { year })
  },

  /**
   * Query current sync status
   */
  getSyncStatus() {
    return api.get('/sync/status')
  },

  // --- Analytics API ---

  getMonthlyTrend(year) {
    return api.get('/analytics/monthly-trend', { params: { year } })
  },

  getLeaveTypeDistribution(year) {
    return api.get('/analytics/leave-type-distribution', { params: { year } })
  },

  getDepartmentComparison(year, metric = 'total') {
    return api.get('/analytics/department-comparison', { params: { year, metric } })
  },

  getWeekdayDistribution(year) {
    return api.get('/analytics/weekday-distribution', { params: { year } })
  },

  getEmployeeRanking(year, limit = 10) {
    return api.get('/analytics/employee-ranking', { params: { year, limit } })
  },

  // --- Trip (business trip / out-of-office) API ---

  /**
   * Get monthly trip summary data (paginated)
   */
  getTripMonthlySummary(params) {
    return api.get('/trip/monthly-summary', {
      params: {
        year: params.year,
        deptId: params.deptId || undefined,
        tripType: params.tripType || undefined,
        employeeName: params.employeeName || undefined,
        page: params.page || 1,
        pageSize: params.pageSize || 10,
        sortBy: params.sortBy || undefined,
        sortOrder: params.sortOrder || 'desc',
      }
    })
  },

  /**
   * Get daily trip detail records for an employee in a specific month
   */
  getTripDailyDetail(params) {
    return api.get('/trip/daily-detail', {
      params: { employeeId: params.employeeId, year: params.year, month: params.month }
    })
  },

  /**
   * Get today's trip/outing list
   */
  getTripToday(params = {}) {
    return api.get('/trip/today', {
      params: {
        deptId: params.deptId || undefined,
        tripType: params.tripType || undefined,
        employeeName: params.employeeName || undefined,
      }
    })
  },

  /**
   * Get trip aggregate stats for a year
   */
  getTripStats(params) {
    return api.get('/trip/stats', {
      params: {
        year: params.year,
        deptId: params.deptId || undefined,
        tripType: params.tripType || undefined,
        employeeName: params.employeeName || undefined,
      }
    })
  },

  /**
   * Get per-day trip/outing headcount for a given month
   */
  getTripDailyCount(params) {
    return api.get('/trip/daily-count', {
      params: {
        year: params.year, month: params.month,
        deptId: params.deptId || undefined,
        tripType: params.tripType || undefined,
        employeeName: params.employeeName || undefined,
      }
    })
  },

  /**
   * Export trip data as Excel file (returns blob)
   */
  exportTripExcel(params) {
    return api.post('/trip/export', {
      year: params.year,
      deptId: params.deptId || null,
      tripType: params.tripType || null,
      employeeName: params.employeeName || null,
    }, { responseType: 'blob' })
  },

  /**
   * Trigger trip data sync from DingTalk
   * @param {string|null} month - optional YYYY-MM format to force-sync a specific month
   */
  triggerTripSync(month) {
    return api.post('/trip/sync', { month: month || null })
  },
}
