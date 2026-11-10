// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, ApiError } from '../api'
import { refreshSession, session, setContext } from '../session'
import type { Context } from '../types'
const context: Context = {
    user: {
        id: 1,
        email: 'a@example.test',
        role: 'user',
        blocked: false,
        created_at: '2026-01-01',
        deleted_at: null,
    },
    lang: 'ru',
    csrf_token: 'rotated',
    catalog: [],
    search_modes: ['movie'],
    limit_options: ['10'],
    default_mode: 'movie',
    default_limit: '10',
    movie_count: 250,
    marks: {
        '1': { movie_id: '1', watched: true, liked: false, watchlist: false },
    },
}
function response(value: unknown, status = 200) {
    return new Response(JSON.stringify(value), { status })
}
beforeEach(() => {
    session.context = null
    session.lang = 'en'
    session.explicitLanguage = false
    session.error = ''
    session.loading = false
})
afterEach(() => vi.unstubAllGlobals())
it('lets the server select the initial saved or accepted language', async () => {
    const fetcher = vi.fn(async (_url: unknown) => response(context))
    vi.stubGlobal('fetch', fetcher)
    await refreshSession()
    expect(String(fetcher.mock.calls[0]?.[0])).not.toContain('lang=')
    expect(session.lang).toBe('ru')
    expect(document.documentElement.lang).toBe('ru')
    expect(session.context?.csrf_token).toBe('rotated')
})
it('sends an explicitly selected language before context is available', async () => {
    const fetcher = vi.fn(async (_url: unknown) =>
        response({ ...context, lang: 'en' }),
    )
    vi.stubGlobal('fetch', fetcher)
    await refreshSession('en')
    expect(String(fetcher.mock.calls[0]?.[0])).toContain('lang=en')
})
it('clears stale authenticated state when the session expires', async () => {
    session.context = structuredClone(context)
    vi.stubGlobal(
        'fetch',
        vi.fn(async () => response({ error: 'Authentication required' }, 401)),
    )
    await expect(api('/account')).rejects.toBeInstanceOf(ApiError)
    expect(session.context.user).toBeNull()
    expect(session.context.marks).toEqual({})
})
it('replaces auth and CSRF state together after authentication', () => {
    setContext({ ...context, csrf_token: 'first' })
    setContext({ ...context, csrf_token: 'next', user: null, marks: {} })
    expect(session.context?.csrf_token).toBe('next')
    expect(session.context?.user).toBeNull()
    expect(session.context?.marks).toEqual({})
})
it('ignores stale session responses after a language change', async () => {
    let completeFirst: (response: Response) => void = () => {}
    const first = new Promise<Response>((resolve) => {
        completeFirst = resolve
    })
    const fetcher = vi
        .fn()
        .mockReturnValueOnce(first)
        .mockResolvedValueOnce(response({ ...context, lang: 'en' }))
    vi.stubGlobal('fetch', fetcher)
    const pending = refreshSession('ru')
    await refreshSession('en')
    completeFirst(response(context))
    await pending
    expect(session.lang).toBe('en')
    expect(session.context?.lang).toBe('en')
})
it('localizes network failures without exposing implementation details', async () => {
    session.lang = 'ru'
    vi.stubGlobal(
        'fetch',
        vi.fn(async () => {
            throw new TypeError('connection reset')
        }),
    )
    await expect(api('/context')).rejects.toThrow(
        'Не удалось подключиться к серверу. Попробуйте ещё раз.',
    )
})
