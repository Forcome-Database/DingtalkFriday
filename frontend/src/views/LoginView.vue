<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CalendarDays, Loader2, AlertCircle, Smartphone } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth.js'
import api from '../api/index.js'
import { isInDingTalk } from '../utils/auth.js'

const router = useRouter()
const { loginWithDingTalk } = useAuth()

const loading = ref(false)
const error = ref('')
const isDingTalk = ref(false)

/**
 * DingTalk H5 login: load JSAPI and request auth code
 */
async function initDingTalkLogin() {
  loading.value = true
  error.value = ''

  try {
    // Get corpId from backend
    const config = await api.getAuthConfig()
    const corpId = config.corpId

    if (!corpId) {
      error.value = '系统未配置企业ID，请联系管理员'
      loading.value = false
      return
    }

    // Load DingTalk JSAPI dynamically
    await loadDingTalkJSAPI()

    // Request auth code
    // eslint-disable-next-line no-undef
    dd.runtime.permission.requestAuthCode({
      corpId: corpId,
      onSuccess: async (result) => {
        try {
          await loginWithDingTalk(result.code)
          router.push('/')
        } catch (e) {
          error.value = e.response?.data?.detail || '登录失败，请联系管理员开通权限'
          loading.value = false
        }
      },
      onFail: (err) => {
        console.error('DingTalk requestAuthCode failed:', err)
        error.value = '获取钉钉授权码失败'
        loading.value = false
      }
    })
  } catch (e) {
    error.value = '钉钉登录初始化失败'
    loading.value = false
  }
}

/**
 * Dynamically load DingTalk JSAPI script
 */
function loadDingTalkJSAPI() {
  return new Promise((resolve, reject) => {
    if (window.dd) {
      resolve()
      return
    }
    const script = document.createElement('script')
    script.src = 'https://g.alicdn.com/dingding/dingtalk-jsapi/3.0.25/dingtalk.open.js'
    script.onload = resolve
    script.onerror = reject
    document.head.appendChild(script)
  })
}

onMounted(() => {
  isDingTalk.value = isInDingTalk()
  if (isDingTalk.value) {
    initDingTalkLogin()
  }
})
</script>

<template>
  <div class="min-h-screen bg-gradient-to-b from-blue-50 to-white flex items-center justify-center p-4">
    <div class="w-full max-w-sm">
      <!-- Logo and title -->
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-accent/10 mb-4">
          <CalendarDays class="text-accent" :size="32" :stroke-width="1.8" />
        </div>
        <h1 class="text-2xl font-bold text-text-primary">员工请假管理系统</h1>
        <p class="text-sm text-text-secondary mt-2">请通过钉钉工作台访问</p>
      </div>

      <!-- DingTalk auto-login state -->
      <div v-if="isDingTalk" class="bg-white rounded-xl shadow-sm border border-border-default p-6 text-center">
        <template v-if="loading && !error">
          <Loader2 class="animate-spin text-accent mx-auto mb-3" :size="32" />
          <p class="text-sm text-text-secondary">正在通过钉钉自动登录...</p>
        </template>

        <!-- Error with retry -->
        <div v-if="error" class="space-y-3">
          <div class="flex items-center gap-2 text-red-600 justify-center">
            <AlertCircle :size="16" />
            <span class="text-sm">{{ error }}</span>
          </div>
          <button
            class="px-4 py-2 text-sm font-medium text-white bg-accent rounded-lg hover:bg-blue-700 transition-colors"
            @click="initDingTalkLogin"
          >
            重试
          </button>
        </div>
      </div>

      <!-- Non-DingTalk browser: show instructions -->
      <div v-else class="bg-white rounded-xl shadow-sm border border-border-default p-6 text-center space-y-4">
        <Smartphone class="text-text-tertiary mx-auto" :size="40" :stroke-width="1.5" />
        <div>
          <p class="text-sm font-medium text-text-primary">请在钉钉中打开</p>
          <p class="text-xs text-text-tertiary mt-2">
            本系统仅支持通过钉钉工作台登录访问，<br/>请打开钉钉 → 工作台 → 找到本应用
          </p>
        </div>
        <div class="pt-2 border-t border-border-default">
          <p class="text-xs text-text-tertiary">
            如需开通权限，请联系管理员
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
