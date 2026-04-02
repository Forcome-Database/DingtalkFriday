<script setup>
import { X, Clock, CheckCircle, AlertCircle, XCircle, UserMinus } from 'lucide-vue-next'

const props = defineProps({
  /** Whether the modal is visible */
  visible: {
    type: Boolean,
    default: false
  },
  /** Today leave detail data from API */
  data: {
    type: Object,
    default: null
  },
  /** Whether data is loading */
  loading: {
    type: Boolean,
    default: false
  },
  /** Leave type color options from useLeaveData */
  leaveTypeOptions: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['close'])

/** Status badge configuration */
const statusConfig = {
  '已审批': { icon: CheckCircle, class: 'text-green-600 bg-green-50' },
  '审批中': { icon: AlertCircle, class: 'text-yellow-600 bg-yellow-50' },
  '已驳回': { icon: XCircle, class: 'text-red-600 bg-red-50' }
}

const fallbackColor = { bgColor: 'bg-gray-100', textColor: 'text-gray-600' }

function getInitial(name) {
  return name ? name.charAt(0) : '?'
}

function getTypeColor(typeName) {
  const opt = props.leaveTypeOptions.find(t => t.name === typeName)
  return opt || fallbackColor
}

function getStatusConfig(status) {
  return statusConfig[status] || statusConfig['已审批']
}

function onOverlayClick(event) {
  if (event.target === event.currentTarget) {
    emit('close')
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="visible"
        class="fixed inset-0 bg-black/40 z-50"
        @click="onOverlayClick"
      >
        <Transition name="slide">
          <div
            v-if="visible"
            class="absolute right-0 top-0 bottom-0 w-full sm:w-[480px] max-w-full bg-white shadow-2xl flex flex-col"
            @click.stop
          >
            <!-- Panel header -->
            <div class="flex items-center justify-between p-4 sm:p-6 pb-4 border-b border-border-default">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-red-50 flex items-center justify-center flex-shrink-0">
                  <UserMinus :size="20" class="text-red-500" />
                </div>
                <div>
                  <div class="text-base font-semibold text-text-primary">今日请假详情</div>
                  <div class="text-[13px] text-text-secondary mt-0.5">
                    共 <span class="font-medium text-text-primary">{{ data?.count ?? 0 }}</span> 人请假
                  </div>
                </div>
              </div>
              <button
                class="w-8 h-8 flex items-center justify-center rounded-md hover:bg-surface text-text-tertiary hover:text-text-primary transition-colors"
                @click="emit('close')"
              >
                <X :size="20" />
              </button>
            </div>

            <!-- Panel body -->
            <div class="flex-1 overflow-y-auto p-4 sm:p-6">
              <!-- Loading skeleton -->
              <div v-if="loading" class="space-y-3">
                <div v-for="i in 3" :key="i" class="rounded-xl border-[1.5px] border-border-default p-4 animate-pulse">
                  <div class="flex items-center gap-3 mb-3">
                    <div class="w-8 h-8 rounded-full bg-gray-200" />
                    <div class="flex-1">
                      <div class="h-4 bg-gray-200 rounded w-24 mb-1.5" />
                      <div class="h-3 bg-gray-100 rounded w-32" />
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <div class="h-5 bg-gray-100 rounded w-12" />
                    <div class="h-4 bg-gray-100 rounded w-28" />
                  </div>
                </div>
              </div>

              <template v-else-if="data">
                <!-- Empty state -->
                <div
                  v-if="data.records && data.records.length === 0"
                  class="flex flex-col items-center justify-center py-16 text-text-tertiary"
                >
                  <UserMinus :size="48" class="mb-3 opacity-30" />
                  <span class="text-sm">今日无人请假</span>
                </div>

                <!-- Records list -->
                <div v-else class="space-y-3">
                  <div
                    v-for="(record, idx) in data.records"
                    :key="idx"
                    class="rounded-xl border-[1.5px] border-border-default p-3 sm:p-4"
                  >
                    <div class="flex items-start justify-between mb-2">
                      <div class="flex items-center gap-2.5">
                        <img
                          v-if="record.avatar"
                          :src="record.avatar"
                          :alt="record.name"
                          class="w-8 h-8 rounded-full object-cover flex-shrink-0"
                        />
                        <div
                          v-else
                          class="w-8 h-8 rounded-full bg-accent text-white text-sm font-semibold flex items-center justify-center flex-shrink-0"
                        >
                          {{ getInitial(record.name) }}
                        </div>
                        <div>
                          <div class="text-sm font-medium text-text-primary">{{ record.name }}</div>
                          <div class="text-[12px] text-text-tertiary">{{ record.deptName }}</div>
                        </div>
                      </div>
                      <div
                        class="flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium flex-shrink-0"
                        :class="getStatusConfig(record.status).class"
                      >
                        <component :is="getStatusConfig(record.status).icon" :size="12" />
                        {{ record.status }}
                      </div>
                    </div>

                    <div class="flex items-center gap-2 flex-wrap">
                      <span
                        class="inline-flex items-center px-2 py-0.5 rounded text-[12px] font-medium"
                        :class="[getTypeColor(record.leaveType).bgColor, getTypeColor(record.leaveType).textColor]"
                      >
                        {{ record.leaveType }}
                      </span>
                      <div class="flex items-center gap-1 text-[13px] text-text-secondary">
                        <Clock :size="13" class="text-text-tertiary" />
                        <span>{{ record.timeDisplay }}</span>
                      </div>
                      <span class="text-[13px] text-text-tertiary">
                        {{ record.durationDisplay }}
                      </span>
                    </div>
                  </div>
                </div>
              </template>
            </div>

            <!-- Panel footer -->
            <div
              v-if="data && data.records && data.records.length > 0"
              class="border-t border-border-default px-4 sm:px-6 py-4 bg-surface"
            >
              <div class="flex items-center justify-between">
                <span class="text-[13px] font-medium text-text-secondary">今日请假</span>
                <span class="text-sm font-semibold text-text-primary">
                  共 {{ data.count }} 人 · {{ data.records.length }} 条记录
                </span>
              </div>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}
.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}
</style>
