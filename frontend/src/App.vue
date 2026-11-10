<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { refreshSession, session, setContext } from './session'
import { t } from './i18n'
import type { Context, Language } from './types'
const route = useRoute(),
    router = useRouter(),
    busy = ref(false),
    error = ref('')
watch(
    () => route.query.lang,
    async (value) => {
        await refreshSession(
            value === 'ru' || value === 'en' ? value : undefined,
        )
        document.title = t('Your next movie')
    },
    { immediate: true },
)
function link(path: string) {
    return { path, query: { lang: session.lang } }
}
function language(lang: Language) {
    return { path: route.path, query: { ...route.query, lang } }
}
async function logout() {
    if (busy.value) return
    busy.value = true
    error.value = ''
    try {
        setContext(await api<Context>('/logout', { method: 'POST', body: {} }))
        await router.push(link('/'))
    } catch (cause) {
        error.value = cause instanceof Error ? cause.message : String(cause)
    } finally {
        busy.value = false
    }
}
</script>
<template>
    <main>
        <nav :aria-label="t('Navigation')">
            <RouterLink
                :to="link('/')"
                :aria-current="route.path === '/' ? 'page' : undefined"
                >{{ t('Search') }}</RouterLink
            >
            <template v-if="session.context?.user">
                <RouterLink
                    :to="link('/account')"
                    :aria-current="
                        route.path === '/account' ? 'page' : undefined
                    "
                    >{{ t('Account') }}</RouterLink
                >
                <RouterLink
                    v-if="session.context.user.role === 'admin'"
                    :to="link('/admin/users')"
                    :aria-current="
                        route.path.startsWith('/admin') ? 'page' : undefined
                    "
                    >{{ t('Users') }}</RouterLink
                >
            </template>
            <template v-else
                ><RouterLink :to="link('/login')">{{ t('Log in') }}</RouterLink
                ><RouterLink :to="link('/register')">{{
                    t('Register')
                }}</RouterLink></template
            >
            <div class="language-switcher">
                <RouterLink
                    v-for="lang in ['en', 'ru'] as const"
                    :key="lang"
                    :to="language(lang)"
                    :lang="lang"
                    :hreflang="lang"
                    :aria-current="session.lang === lang ? 'true' : undefined"
                    >{{ lang.toUpperCase() }}</RouterLink
                >
            </div>
            <form
                v-if="session.context?.user"
                class="logout"
                @submit.prevent="logout"
            >
                <button class="button-danger" :disabled="busy">
                    {{ t('Log out') }}
                </button>
            </form>
        </nav>
        <p v-if="error" role="alert" class="error">{{ error }}</p>
        <p v-if="session.loading" role="status">{{ t('Loading…') }}</p>
        <div v-else-if="session.error">
            <p role="alert" class="error">{{ session.error }}</p>
            <button @click="refreshSession()">{{ t('Retry') }}</button>
        </div>
        <RouterView v-else-if="session.context" />
    </main>
</template>
