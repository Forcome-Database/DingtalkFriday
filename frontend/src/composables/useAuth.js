/**
 * Authentication state management composable.
 * Provides reactive user state and login/logout methods.
 */

import { computed, reactive, ref } from 'vue'
import api from '../api/index.js'
import {
  getToken,
  getUser,
  isInDingTalk,
  removeToken,
  removeUser,
  setToken,
  setUser
} from '../utils/auth.js'

// Shared reactive state (singleton across components)
const currentUser = ref(getUser())
const token = ref(getToken())

export function useAuth() {
  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => currentUser.value?.isAdmin === true)

  /**
   * Login via DingTalk H5 authCode exchange.
   * @param {string} authCode - Code from dd.runtime.permission.requestAuthCode
   */
  async function loginWithDingTalk(authCode) {
    const res = await api.loginDingTalk({ authCode })
    token.value = res.token
    currentUser.value = res.user
    setToken(res.token)
    setUser(res.user)
  }

  /**
   * Clear auth state and redirect to login page.
   */
  function logout() {
    token.value = null
    currentUser.value = null
    removeToken()
    removeUser()
  }

  /**
   * Refresh current user info from server.
   */
  async function refreshUser() {
    try {
      const user = await api.getMe()
      currentUser.value = user
      setUser(user)
    } catch {
      // Token invalid, clear state
      logout()
    }
  }

  return {
    currentUser,
    token,
    isLoggedIn,
    isAdmin,
    isInDingTalk,
    loginWithDingTalk,
    logout,
    refreshUser,
  }
}
