<script setup>
import { Users, CalendarDays, TrendingUp, PieChart, UserMinus } from 'lucide-vue-next'

const props = defineProps({
  /** Statistics data object from API */
  stats: {
    type: Object,
    default: () => ({
      totalCount: 0,
      totalDays: 0,
      avgDays: 0,
      annualRatio: 0,
      annualDays: 0
    })
  },
  /** Current display unit: 'day' or 'hour' */
  unit: {
    type: String,
    default: 'day'
  },
  /** Today's leave headcount */
  todayLeaveCount: {
    type: Number,
    default: 0
  }
})
</script>

<template>
  <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
    <!-- Card 1: Total leave count -->
    <div class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5">
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">请假总人次</span>
        <div class="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center">
          <Users :size="18" class="text-accent" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-text-primary leading-none">
          {{ stats.totalCount }}
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">人次</span>
      </div>
    </div>

    <!-- Card 2: Total leave days -->
    <div class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5">
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">请假总{{ unit === 'hour' ? '时长' : '天数' }}</span>
        <div class="w-9 h-9 rounded-lg bg-green-50 flex items-center justify-center">
          <CalendarDays :size="18" class="text-green-600" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-accent leading-none">
          {{ stats.totalDays }}
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">{{ unit === 'hour' ? '小时' : '天' }}</span>
      </div>
    </div>

    <!-- Card 3: Average leave per person -->
    <div class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5">
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">人均请假</span>
        <div class="w-9 h-9 rounded-lg bg-orange-50 flex items-center justify-center">
          <TrendingUp :size="18" class="text-orange-500" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-text-primary leading-none">
          {{ stats.avgDays }}
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">{{ unit === 'hour' ? '小时/人' : '天/人' }}</span>
      </div>
    </div>

    <!-- Card 4: Annual leave ratio -->
    <div class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5">
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">年假占比</span>
        <div class="w-9 h-9 rounded-lg bg-purple-50 flex items-center justify-center">
          <PieChart :size="18" class="text-purple-600" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-accent leading-none">
          {{ stats.annualRatio }}%
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">
          {{ stats.annualDays }} {{ unit === 'hour' ? '小时' : '天' }}
        </span>
      </div>
    </div>

    <!-- Card 5: Today's leave count -->
    <div class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5">
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">今日请假</span>
        <div class="w-9 h-9 rounded-lg bg-red-50 flex items-center justify-center">
          <UserMinus :size="18" class="text-red-500" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-text-primary leading-none">
          {{ todayLeaveCount }}
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">人</span>
      </div>
    </div>
  </div>
</template>
