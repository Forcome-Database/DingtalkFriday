import { ref, watch } from 'vue'
import api from '../api/index.js'

/**
 * Composable for managing trip analytics dashboard data.
 * Provides year-based data fetching for all trip analytics charts.
 */
export function useTripAnalyticsData(yearRef) {
  const loading = ref(false)

  // Chart data refs
  const monthlyTrend = ref(null)
  const typeDistribution = ref(null)
  const departmentComparison = ref(null)
  const weekdayDistribution = ref(null)
  const employeeRanking = ref(null)

  async function fetchAll(targetYear) {
    loading.value = true
    try {
      const [trendData, typeData, deptData, weekdayData, rankingData] = await Promise.all([
        api.getTripMonthlyTrend(targetYear).catch(err => {
          console.error('[TripAnalytics] Failed to fetch monthly trend:', err)
          return null
        }),
        api.getTripTypeDistribution(targetYear).catch(err => {
          console.error('[TripAnalytics] Failed to fetch type distribution:', err)
          return null
        }),
        api.getTripDepartmentComparison(targetYear).catch(err => {
          console.error('[TripAnalytics] Failed to fetch department comparison:', err)
          return null
        }),
        api.getTripWeekdayDistribution(targetYear).catch(err => {
          console.error('[TripAnalytics] Failed to fetch weekday distribution:', err)
          return null
        }),
        api.getTripEmployeeRanking(targetYear).catch(err => {
          console.error('[TripAnalytics] Failed to fetch employee ranking:', err)
          return null
        }),
      ])

      monthlyTrend.value = trendData
      typeDistribution.value = typeData
      departmentComparison.value = deptData
      weekdayDistribution.value = weekdayData
      employeeRanking.value = rankingData
    } catch (err) {
      console.error('[TripAnalytics] Unexpected error in fetchAll:', err)
      monthlyTrend.value = null
      typeDistribution.value = null
      departmentComparison.value = null
      weekdayDistribution.value = null
      employeeRanking.value = null
    } finally {
      loading.value = false
    }
  }

  // Watch year prop changes and re-fetch
  watch(yearRef, (newYear) => {
    fetchAll(newYear)
  })

  return {
    loading,
    monthlyTrend,
    typeDistribution,
    departmentComparison,
    weekdayDistribution,
    employeeRanking,
    fetchAll,
  }
}
