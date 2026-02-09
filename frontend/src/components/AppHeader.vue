<script setup>
import { CalendarDays, RefreshCw, Download, LogOut, Shield } from 'lucide-vue-next'

const props = defineProps({
  /** Whether a sync operation is currently in progress */
  syncing: {
    type: Boolean,
    default: false
  },
  /** Whether an export operation is currently in progress */
  exporting: {
    type: Boolean,
    default: false
  },
  /** Year to display on sync button */
  syncYear: {
    type: Number,
    default: new Date().getFullYear()
  },
  /** Currently active page: 'export', 'analytics', or 'admin' */
  activePage: {
    type: String,
    default: 'export'
  },
  /** Current logged-in user object */
  currentUser: {
    type: Object,
    default: null
  },
  /** Whether current user is admin */
  isAdmin: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['sync', 'export', 'page-change', 'logout'])
</script>

<template>
  <header
    class="flex items-center justify-between h-14 sm:h-16 px-4 sm:px-6 lg:px-8 border-b border-border-default bg-white"
  >
    <!-- Left: Logo, title, and navigation tabs -->
    <div class="flex items-center gap-3">
      <CalendarDays class="text-accent" :size="28" :stroke-width="1.8" />
      <span class="text-lg font-semibold text-text-primary hidden sm:inline">员工请假管理系统</span>

      <!-- Navigation tabs -->
      <nav class="flex items-center gap-1 ml-4">
        <button
          class="px-3 py-1.5 text-[13px] rounded-md transition-colors"
          :class="activePage === 'export'
            ? 'bg-highlight text-accent font-semibold'
            : 'text-text-secondary font-medium hover:text-text-primary'"
          @click="emit('page-change', 'export')"
        >
          数据导出
        </button>
        <button
          class="px-3 py-1.5 text-[13px] rounded-md transition-colors"
          :class="activePage === 'analytics'
            ? 'bg-highlight text-accent font-semibold'
            : 'text-text-secondary font-medium hover:text-text-primary'"
          @click="emit('page-change', 'analytics')"
        >
          数据分析
        </button>
        <!-- Admin tab (visible only to admins) -->
        <button
          v-if="isAdmin"
          class="px-3 py-1.5 text-[13px] rounded-md transition-colors flex items-center gap-1"
          :class="activePage === 'admin'
            ? 'bg-highlight text-accent font-semibold'
            : 'text-text-secondary font-medium hover:text-text-primary'"
          @click="emit('page-change', 'admin')"
        >
          <Shield :size="14" />
          用户管理
        </button>
      </nav>
    </div>

    <!-- Right: Actions and user info -->
    <div class="flex items-center gap-2 sm:gap-3 lg:gap-4">
      <!-- Sync button (admin only, hidden on analytics/admin page) -->
      <button
        v-if="activePage === 'export' && isAdmin"
        class="flex items-center gap-1.5 sm:gap-2 px-2 sm:px-3 lg:px-4 py-2 text-sm font-medium text-text-secondary border border-border-default rounded-lg hover:bg-surface transition-colors"
        :disabled="syncing"
        @click="emit('sync')"
      >
        <RefreshCw
          :size="16"
          :class="{ 'animate-spin': syncing }"
        />
        <span class="hidden sm:inline">{{ syncing ? '同步中...' : `同步 ${syncYear} 数据` }}</span>
      </button>

      <!-- Export Excel button (hidden on analytics/admin page) -->
      <button
        v-if="activePage === 'export'"
        class="flex items-center gap-1.5 sm:gap-2 px-2 sm:px-3 lg:px-5 py-2 text-sm font-semibold text-white bg-accent rounded-lg hover:bg-blue-700 transition-colors"
        :disabled="exporting"
        @click="emit('export')"
      >
        <Download :size="16" />
        <span class="hidden sm:inline">{{ exporting ? '导出中...' : '导出 Excel' }}</span>
      </button>

      <!-- Divider -->
      <div class="hidden sm:block w-px h-6 bg-border-default"></div>

      <!-- User info -->
      <div class="hidden sm:flex items-center gap-2">
        <img
          v-if="currentUser?.avatar"
          :src="currentUser.avatar"
          class="w-7 h-7 rounded-full object-cover"
          alt="avatar"
        />
        <div v-else class="w-7 h-7 rounded-full bg-accent/10 flex items-center justify-center text-accent text-xs font-semibold">
          {{ currentUser?.name?.charAt(0) || '?' }}
        </div>
        <span class="text-sm font-medium text-text-secondary max-w-[100px] truncate">
          {{ currentUser?.name || '用户' }}
        </span>
        <span v-if="isAdmin" class="text-[10px] px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded font-medium">
          管理员
        </span>
      </div>

      <!-- Logout button -->
      <button
        class="flex items-center gap-1 px-2 py-1.5 text-xs text-text-tertiary hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
        title="退出登录"
        @click="emit('logout')"
      >
        <LogOut :size="14" />
        <span class="hidden lg:inline">退出</span>
      </button>
    </div>
  </header>
</template>
