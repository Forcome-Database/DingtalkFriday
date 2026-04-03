<script setup>
import { Briefcase, MapPin, CalendarDays, Users } from 'lucide-vue-next'

const props = defineProps({
  /** Trip statistics data object from API */
  stats: {
    type: Object,
    default: () => ({
      totalCount: 0,
      totalDays: 0,
      todayTripCount: 0,
      todayOutingCount: 0,
    })
  }
})

const emit = defineEmits(['todayTripClick', 'todayOutingClick'])
</script>

<template>
  <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
    <!-- Card 1: Total person-trips -->
    <div class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5">
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">总人次</span>
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

    <!-- Card 2: Total days -->
    <div class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5">
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">总天数</span>
        <div class="w-9 h-9 rounded-lg bg-green-50 flex items-center justify-center">
          <CalendarDays :size="18" class="text-green-600" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-accent leading-none">
          {{ stats.totalDays }}
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">天</span>
      </div>
    </div>

    <!-- Card 3: Today business trip (clickable) -->
    <div
      class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5 cursor-pointer hover:border-accent/40 hover:shadow-sm transition-all"
      @click="emit('todayTripClick')"
    >
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">今日出差</span>
        <div class="w-9 h-9 rounded-lg bg-orange-50 flex items-center justify-center">
          <Briefcase :size="18" class="text-orange-600" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-orange-600 leading-none">
          {{ stats.todayTripCount }}
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">人</span>
      </div>
    </div>

    <!-- Card 4: Today out-of-office (clickable) -->
    <div
      class="rounded-xl border-[1.5px] border-border-default p-4 sm:p-5 cursor-pointer hover:border-accent/40 hover:shadow-sm transition-all"
      @click="emit('todayOutingClick')"
    >
      <div class="flex items-center justify-between mb-2">
        <span class="text-[13px] font-medium text-text-secondary">今日外出</span>
        <div class="w-9 h-9 rounded-lg bg-purple-50 flex items-center justify-center">
          <MapPin :size="18" class="text-purple-600" />
        </div>
      </div>
      <div class="flex items-end gap-2">
        <span class="text-xl sm:text-2xl lg:text-[28px] font-bold text-purple-600 leading-none">
          {{ stats.todayOutingCount }}
        </span>
        <span class="text-[13px] text-text-tertiary pb-0.5">人</span>
      </div>
    </div>
  </div>
</template>
