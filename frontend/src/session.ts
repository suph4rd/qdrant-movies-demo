import { reactive } from 'vue'
import type { Context, Language } from './types'
import { api } from './api'
export const session = reactive<{
    context: Context | null
    lang: Language
    loading: boolean
    error: string
    explicitLanguage: boolean
}>({
    context: null,
    lang: 'en',
    loading: false,
    error: '',
    explicitLanguage: false,
})
export function setContext(context: Context) {
    session.context = context
    session.lang = context.lang
    document.documentElement.lang = context.lang
}
let revision = 0
export async function refreshSession(lang?: Language) {
    const current = ++revision
    if (lang) {
        session.lang = lang
        session.explicitLanguage = true
    }
    session.loading = true
    session.error = ''
    try {
        const context = await api<Context>('/context')
        if (current === revision) setContext(context)
    } catch (error) {
        if (current === revision)
            session.error =
                error instanceof Error ? error.message : String(error)
    } finally {
        if (current === revision) session.loading = false
    }
}
