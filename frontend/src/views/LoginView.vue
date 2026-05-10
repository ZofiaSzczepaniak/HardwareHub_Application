<template>
  <div class="login-page">
    <div class="login-box login-box--blurred">

      <!-- Logo placeholder -->
      <div class="logo-placeholder">
        <div class="logo-square">Logo</div>
      </div>

      <h1 class="login-heading">Welcome back</h1>

      <form @submit.prevent="submit" class="login-form">

        <!-- Email -->
        <div class="field">
          <label class="field-label">Email</label>
          <input
            v-model="username"
            class="field-input"
            type="text"
            placeholder="you@domain.com"
            autocomplete="username"
            required
          />
          <p v-if="domainError" class="field-error">
            Invalid format. Please use @domain.com format
          </p>
        </div>

        <!-- Password -->
        <div class="field">
          <label class="field-label">Password</label>
          <input
            v-model="password"
            type="password"
            class="field-input"
            placeholder="••••••••"
            autocomplete="current-password"
            required
          />
        </div>

        <!-- Server error -->
        <p v-if="error" class="server-error">{{ error }}</p>

        <button type="submit" class="login-btn" :disabled="loading || domainError || !username">
          <span v-if="loading" class="spin"></span>
          <span v-else>Login</span>
        </button>

      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const auth   = useAuthStore()
const router = useRouter()

const username = ref('')
const password = ref('')
const loading  = ref(false)
const error    = ref('')

const domainError = computed(() =>
  username.value.includes('@') && !username.value.endsWith('.com')
)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    router.push('/')
  } catch (e) {
    error.value = e?.response?.data?.detail || 'Login failed'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-2);
}

.login-box {
  width: 100%;
  max-width: 380px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 40px 36px;
}

/* ── Logo ── */
.logo-placeholder {
  display: flex;
  justify-content: center;
  margin-bottom: 24px;
}
.logo-square {
  width: 52px;
  height: 52px;
  border: 2px solid var(--accent);
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--mono);
  font-size: 16px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: .04em;
}

/* ── Heading ── */
.login-heading {
  text-align: center;
  font-size: 1.4rem;
  margin-bottom: 28px;
}

/* ── Soft edges ── */
.login-box--blurred {
  box-shadow:
    0 0 0 1px var(--border),
    0 8px 32px rgba(0, 0, 0, .08),
    0 2px 8px rgba(0, 0, 0, .04);
  border: none;
}

/* ── Form ── */
.login-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.field-label {
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-dim);
}
.field-input {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-family: var(--sans);
  font-size: 14px;
  padding: 10px 12px;
  outline: none;
  transition: border-color var(--transition);
}
.field-input:focus { border-color: var(--accent); }
.field-input::placeholder { color: var(--text-dim); }

.field-error {
  font-size: 12px;
  color: var(--red);
  margin-top: 2px;
}

.server-error {
  font-size: 13px;
  color: var(--red);
  background: var(--red-bg);
  border: 1px solid var(--red-border);
  border-radius: var(--radius);
  padding: 8px 12px;
}

/* ── Button ── */
.login-btn {
  width: 100%;
  padding: 12px;
  margin-top: 4px;
  background: var(--accent);
  color: #fff;
  border: 1px solid var(--accent);
  border-radius: var(--radius);
  font-family: var(--sans);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: background var(--transition), border-color var(--transition);
}
.login-btn:hover:not(:disabled) { background: var(--accent-dim); border-color: var(--accent-dim); }
.login-btn:disabled { opacity: .45; cursor: not-allowed; }
</style>
