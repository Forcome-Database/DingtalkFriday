import { ref } from 'vue'
import api from '../api/index.js'

/**
 * Composable for managing analytics dashboard data.
 * Provides year-based data fetching for all analytics charts.
 */
export function useAnalyticsData() {
  const currentYear = new Date().getFullYear()

  // --- State ---
  const year = ref(currentYear)
  const loading = ref(false)

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
    loading.value = true
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
        api.getDepartmentComparison(targetYear).catch(err => {
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

      monthlyTrend.value = trendData
      leaveTypeDistribution.value = typeData
      departmentComparison.value = deptData
      weekdayDistribution.value = weekdayData
      employeeRanking.value = rankingData
    } catch (err) {
      console.error('[Analytics] Unexpected error in fetchAll:', err)
      monthlyTrend.value = null
      leaveTypeDistribution.value = null
      departmentComparison.value = null
      weekdayDistribution.value = null
      employeeRanking.value = null
    } finally {
      loading.value = false
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
    monthlyTrend,
    leaveTypeDistribution,
    departmentComparison,
    weekdayDistribution,
    employeeRanking,

    // Methods
    fetchAll,
    switchYear
  }
}
