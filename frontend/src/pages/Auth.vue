<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { session, setContext } from '../session'
import { t } from '../i18n'
import type { Context } from '../types'
const route = useRoute(),
    router = useRouter(),
    email = ref(''),
    password = ref(''),
    repeat = ref(''),
    busy = ref(false),
    error = ref('')
const registration = computed(() => route.path === '/register')
async function submit() {
    if (busy.value) return
    busy.value = true
    error.value = ''
    try {
        setContext(
            await api<Context>(registration.value ? '/register' : '/login', {
                method: 'POST',
                body: {
                    email: email.value,
                    password: password.value,
                    ...(registration.value
                        ? { password_repeat: repeat.value }
                        : {}),
                },
            }),
        )
        password.value = ''
        repeat.value = ''
        await router.push({ path: '/account', query: { lang: session.lang } })
    } catch (cause) {
        error.value = cause instanceof Error ? cause.message : String(cause)
    } finally {
        busy.value = false
    }
}
</script>
<template>
    <h1>{{ t(registration ? 'Register' : 'Log in') }}</h1>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <form class="account-form" @submit.prevent="submit" :aria-busy="busy">
        <label for="email">{{ t('Email') }}</label
        ><input
            id="email"
            v-model="email"
            type="email"
            autocomplete="email"
            maxlength="254"
            required
        />
        <label for="password">{{ t('Password') }}</label
        ><input
            id="password"
            v-model="password"
            type="password"
            :autocomplete="registration ? 'new-password' : 'current-password'"
            :minlength="registration ? 12 : undefined"
            maxlength="128"
            required
            :aria-describedby="registration ? 'password-hint' : undefined"
        />
        <template v-if="registration"
            ><p id="password-hint" class="muted">
                {{ t('Use 12–128 characters.') }}
            </p>
            <label for="password-repeat">{{ t('Repeat password') }}</label
            ><input
                id="password-repeat"
                v-model="repeat"
                type="password"
                autocomplete="new-password"
                minlength="12"
                maxlength="128"
                required
        /></template>
        <button :disabled="busy">
            {{ t(registration ? 'Register' : 'Log in') }}
        </button>
        <p v-if="busy" role="status">{{ t('Loading…') }}</p>
    </form>
</template>
