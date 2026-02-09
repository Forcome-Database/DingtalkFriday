<script setup>
import { CalendarDays, RefreshCw, Download, LogOut, Shield, FileSpreadsheet, BarChart3 } from 'lucide-vue-next'

const props = defineProps({
  syncing: { type: Boolean, default: false },
  exporting: { type: Boolean, default: false },
  syncYear: { type: Number, default: new Date().getFullYear() },
  activePage: { type: String, default: 'export' },
  currentUser: { type: Object, default: null },
  isAdmin: { type: Boolean, default: false }
})

const emit = defineEmits(['sync', 'export', 'page-change', 'logout'])
</script>

<template>
  <!-- ===== Desktop header (sm+): single row, everything visible ===== -->
  <header
    class="hidden sm:flex items-center justify-between h-16 px-6 lg:px-8 border-b border-border-default bg-white"
  >
    <div class="flex items-center gap-3">
      <CalendarDays class="text-accent" :size="28" :stroke-width="1.8" />
      <span class="text-lg font-semibold text-text-primary">员工请假管理系统</span>

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

    <div class="flex items-center gap-3 lg:gap-4">
      <button
        v-if="activePage === 'export' && isAdmin"
        class="flex items-center gap-2 px-3 lg:px-4 py-2 text-sm font-medium text-text-secondary border border-border-default rounded-lg hover:bg-surface transition-colors"
        :disabled="syncing"
        @click="emit('sync')"
      >
        <RefreshCw :size="16" :class="{ 'animate-spin': syncing }" />
        {{ syncing ? '同步中...' : `同步 ${syncYear} 数据` }}
      </button>

      <button
        v-if="activePage === 'export'"
        class="flex items-center gap-2 px-3 lg:px-5 py-2 text-sm font-semibold text-white bg-accent rounded-lg hover:bg-blue-700 transition-colors"
        :disabled="exporting"
        @click="emit('export')"
      >
        <Download :size="16" />
        {{ exporting ? '导出中...' : '导出 Excel' }}
      </button>

      <div class="w-px h-6 bg-border-default"></div>

      <div class="flex items-center gap-2">
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

      <button
        class="flex items-center gap-1 px-2 py-1.5 text-xs text-text-tertiary hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
        @click="emit('logout')"
      >
        <LogOut :size="14" />
        <span class="hidden lg:inline">退出</span>
      </button>
    </div>
  </header>

  <!-- ===== Mobile top bar (<sm): slim, only action buttons ===== -->
  <header
    class="flex sm:hidden items-center justify-between h-11 px-4 border-b border-border-default bg-white"
  >
    <span class="text-sm font-medium text-text-secondary truncate">
      {{ currentUser?.name || '用户' }}
      <span v-if="isAdmin" class="text-[10px] ml-1 px-1 py-0.5 bg-amber-100 text-amber-700 rounded font-medium">管理员</span>
    </span>

    <div class="flex items-center gap-1">
      <button
        v-if="activePage === 'export' && isAdmin"
        class="p-2 rounded-lg transition-colors"
        :class="syncing ? 'text-accent' : 'text-text-tertiary active:bg-gray-100'"
        :disabled="syncing"
        @click="emit('sync')"
      >
        <RefreshCw :size="18" :class="{ 'animate-spin': syncing }" />
      </button>
      <button
        v-if="activePage === 'export'"
        class="p-2 text-white bg-accent rounded-lg active:bg-blue-700 transition-colors"
        :disabled="exporting"
        @click="emit('export')"
      >
        <Download :size="18" />
      </button>
      <button
        class="p-2 text-text-tertiary active:text-red-600 active:bg-red-50 rounded-lg transition-colors"
        @click="emit('logout')"
      >
        <LogOut :size="18" />
      </button>
    </div>
  </header>

  <!-- ===== Mobile bottom TabBar (<sm) ===== -->
  <nav
    class="fixed sm:hidden bottom-0 left-0 right-0 z-50 flex items-stretch bg-white border-t border-border-default"
    style="padding-bottom: env(safe-area-inset-bottom)"
  >
    <button
      class="flex-1 flex flex-col items-center justify-center gap-0.5 py-2 transition-colors"
      :class="activePage === 'export' ? 'text-accent' : 'text-text-tertiary'"
      @click="emit('page-change', 'export')"
    >
      <FileSpreadsheet :size="20" :stroke-width="activePage === 'export' ? 2.2 : 1.6" />
      <span class="text-[10px] font-medium">数据导出</span>
    </button>
    <button
      class="flex-1 flex flex-col items-center justify-center gap-0.5 py-2 transition-colors"
      :class="activePage === 'analytics' ? 'text-accent' : 'text-text-tertiary'"
      @click="emit('page-change', 'analytics')"
    >
      <BarChart3 :size="20" :stroke-width="activePage === 'analytics' ? 2.2 : 1.6" />
      <span class="text-[10px] font-medium">数据分析</span>
    </button>
    <button
      v-if="isAdmin"
      class="flex-1 flex flex-col items-center justify-center gap-0.5 py-2 transition-colors"
      :class="activePage === 'admin' ? 'text-accent' : 'text-text-tertiary'"
      @click="emit('page-change', 'admin')"
    >
      <Shield :size="20" :stroke-width="activePage === 'admin' ? 2.2 : 1.6" />
      <span class="text-[10px] font-medium">用户管理</span>
    </button>
  </nav>
</template>
