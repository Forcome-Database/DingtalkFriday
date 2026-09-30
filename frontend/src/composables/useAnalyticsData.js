import { ref } from 'vue'
import api from '../api/index.js'
import { businessDateParts } from '../utils/date.js'

/**
 * Composable for managing analytics dashboard data.
 * Provides year-based data fetching for all analytics charts.
 */
export function useAnalyticsData() {
  const currentYear = businessDateParts().year

  // --- State ---
  const year = ref(currentYear)
  const loading = ref(false)
  const deptMetric = ref('total')
  let requestVersion = 0
  let departmentVersion = 0

  // Chart data refs
  const monthlyTrend = ref(null)
  const leaveTypeDistribution = ref(null)
  const departmentComparison = ref(null)
  const weekdayDistribution = ref(null)
  const employeeRanking = ref(null)

  /**
   * Fetch all analytics data for the given year concurrently.
   * @param {number} targetYear - Year to fetch data for
   */
  async function fetchAll(targetYear) {
    const version = ++requestVersion
    const deptVersion = ++departmentVersion
    year.value = targetYear
    loading.value = true
    monthlyTrend.value = null
    leaveTypeDistribution.value = null
    departmentComparison.value = null
    weekdayDistribution.value = null
    employeeRanking.value = null
    try {
      const [
        trendData,
        typeData,
        deptData,
        weekdayData,
        rankingData
      ] = await Promise.all([
        api.getMonthlyTrend(targetYear).catch(err => {
          console.error('[Analytics] Failed to fetch monthly trend:', err)
          return null
        }),
        api.getLeaveTypeDistribution(targetYear).catch(err => {
          console.error('[Analytics] Failed to fetch leave type distribution:', err)
          return null
        }),
        api.getDepartmentComparison(targetYear, deptMetric.value).catch(err => {
          console.error('[Analytics] Failed to fetch department comparison:', err)
          return null
        }),
        api.getWeekdayDistribution(targetYear).catch(err => {
          console.error('[Analytics] Failed to fetch weekday distribution:', err)
          return null
        }),
        api.getEmployeeRanking(targetYear).catch(err => {
          console.error('[Analytics] Failed to fetch employee ranking:', err)
          return null
        })
      ])

      if (version !== requestVersion || year.value !== targetYear) return
      monthlyTrend.value = trendData
      leaveTypeDistribution.value = typeData
      if (deptVersion === departmentVersion) departmentComparison.value = deptData
      weekdayDistribution.value = weekdayData
      employeeRanking.value = rankingData
    } catch (err) {
      if (version !== requestVersion) return
      console.error('[Analytics] Unexpected error in fetchAll:', err)
      monthlyTrend.value = null
      leaveTypeDistribution.value = null
      departmentComparison.value = null
      weekdayDistribution.value = null
      employeeRanking.value = null
    } finally {
      if (version === requestVersion) loading.value = false
    }
  }

  async function fetchDepartmentComparison(metric) {
    deptMetric.value = metric
    const version = ++departmentVersion
    const targetYear = year.value
    departmentComparison.value = null
    try {
      const data = await api.getDepartmentComparison(targetYear, metric)
      if (version === departmentVersion && targetYear === year.value) departmentComparison.value = data
    } catch (err) {
      console.error('[Analytics] Failed to refresh department comparison:', err)
    }
  }

  /**
   * Switch to a different year and re-fetch all data.
   * @param {number} targetYear - Year to switch to
   */
  function switchYear(targetYear) {
    year.value = targetYear
    fetchAll(targetYear)
  }

  return {
    // State
    year,
    loading,
    deptMetric,
    monthlyTrend,
    leaveTypeDistribution,
    departmentComparison,
    weekdayDistribution,
    employeeRanking,

    // Methods
    fetchAll,
    fetchDepartmentComparison,
    switchYear
  }
}
