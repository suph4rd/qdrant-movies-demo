import { session } from './session'
import { t } from './i18n'
export class ApiError extends Error {
    constructor(
        message: string,
        public status: number,
        public code?: string,
        public task_id?: string,
    ) {
        super(message)
    }
}
export async function api<T>(
    path: string,
    options: {
        method?: string
        body?: unknown
        query?: Record<string, string>
    } = {},
): Promise<T> {
    const query = new URLSearchParams({ ...options.query })
    if (session.context || session.explicitLanguage)
        query.set('lang', session.lang)
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (options.body !== undefined) headers['Content-Type'] = 'application/json'
    if (options.method && options.method !== 'GET')
        headers['X-CSRF-Token'] = session.context?.csrf_token || ''
    let response: Response
    try {
        response = await fetch(`/api${path}?${query}`, {
            method: options.method || 'GET',
            headers,
            credentials: 'same-origin',
            body:
                options.body === undefined
                    ? undefined
                    : JSON.stringify(options.body),
        })
    } catch {
        throw new ApiError(t('Cannot connect to the server. Try again.'), 0)
    }
    const data = await response.json().catch(() => null)
    if (!response.ok) {
        if (response.status === 401 && session.context) {
            session.context.user = null
            session.context.marks = {}
        }
        throw new ApiError(
            data?.error || t('The request failed. Try again.'),
            response.status,
            data?.code,
            data?.task_id,
        )
    }
    return data as T
}
