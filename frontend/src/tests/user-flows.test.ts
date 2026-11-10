// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import Search from '../pages/Search.vue'
import Auth from '../pages/Auth.vue'
import Account from '../pages/Account.vue'
import MovieMarks from '../components/MovieMarks.vue'
import { resetTasks, searchTasks } from '../searchTasks'
import { session, setContext } from '../session'
import type { Context, Movie, MovieList } from '../types'
const movie: Movie = {
    id: '18446744073709551615',
    title: 'A movie',
    year: 2000,
    genres: ['Drama'],
    description: 'A description',
    mark_reference: 'verified-card',
}
const context: Context = {
    user: {
        id: 1,
        email: 'user@example.test',
        role: 'user',
        blocked: false,
        created_at: '2026-01-01',
        deleted_at: null,
    },
    lang: 'en',
    csrf_token: 'csrf',
    catalog: [movie],
    search_modes: ['movie', 'description'],
    limit_options: ['5', '10'],
    default_mode: 'movie',
    default_limit: '10',
    movie_count: 250,
    marks: {},
}
function response(value: unknown, status = 200) {
    return new Response(JSON.stringify(value), {
        status,
        headers: { 'Content-Type': 'application/json' },
    })
}
async function setup(component: typeof Search, path: string) {
    const router = createRouter({
        history: createMemoryHistory(),
        routes: [{ path: '/:pathMatch(.*)*', component }],
    })
    await router.push(path)
    await router.isReady()
    const wrapper = mount(component, { global: { plugins: [router] } })
    await flushPromises()
    return { wrapper, router }
}
beforeEach(() => { setContext(structuredClone(context)); resetTasks() })
afterEach(() => vi.unstubAllGlobals())
describe('user flows', () => {
    it('submits a search once and restores saved results using GET through history', async () => {
        const fetcher = vi.fn(async (_url: unknown, options?: RequestInit) =>
            options?.method === 'POST'
                ? response({ token: 'saved' })
                : response({
                      result: {
                          messages: ['Imported'],
                          groups: [{ source: movie, recommendations: [] }],
                      },
                      marks: {},
                      movie_count: 251,
                  }),
        )
        vi.stubGlobal('fetch', fetcher)
        const { wrapper, router } = await setup(Search, '/?lang=en')
        await wrapper.get('#query').setValue('new film')
        await wrapper.get('form').trigger('submit')
        await flushPromises()
        expect(router.currentRoute.value.query.result).toBe('saved')
        expect(
            fetcher.mock.calls.filter(
                ([, options]) => options?.method === 'POST',
            ),
        ).toHaveLength(1)
        expect(wrapper.text()).toContain('Imported')
        expect(session.context?.movie_count).toBe(251)
        await router.push('/?q=old&mode=movie&limit=5&result=older&lang=en')
        await flushPromises()
        router.back()
        await flushPromises()
        expect(
            fetcher.mock.calls.filter(
                ([, options]) => options?.method === 'POST',
            ),
        ).toHaveLength(1)
        expect(wrapper.get<HTMLInputElement>('#query').element.value).toBe(
            'new film',
        )
        wrapper.unmount()
    })
    it('preserves large IDs and verified references when setting mutually exclusive marks', async () => {
        const fetcher = vi.fn(async (_url: unknown, _options?: RequestInit) =>
            response({
                marks: {
                    [movie.id]: {
                        movie_id: movie.id,
                        watched: true,
                        liked: false,
                        watchlist: false,
                    },
                },
            }),
        )
        vi.stubGlobal('fetch', fetcher)
        const wrapper = mount(MovieMarks, { props: { movie } })
        await wrapper.findAll('button')[0]!.trigger('click')
        await flushPromises()
        const options = fetcher.mock.calls[0]?.[1] as RequestInit | undefined
        expect(JSON.parse(options?.body as string)).toEqual({
            movie_id: movie.id,
            reference: 'verified-card',
            flag: 'watched',
            state: true,
        })
        expect(
            (options?.headers as Record<string, string>)['X-CSRF-Token'],
        ).toBe('csrf')
        expect(session.context?.marks[movie.id]?.watched).toBe(true)
        expect(wrapper.findAll('button')[0]!.attributes('aria-pressed')).toBe(
            'true',
        )
        wrapper.unmount()
    })
    it('rotates session state after login and navigates to account', async () => {
        const fetcher = vi.fn(async (_url: unknown, _options?: RequestInit) =>
            response({ ...context, csrf_token: 'rotated' }),
        )
        vi.stubGlobal('fetch', fetcher)
        const { wrapper, router } = await setup(Auth, '/login?lang=en')
        await wrapper.get('#email').setValue('user@example.test')
        await wrapper.get('#password').setValue('long-password')
        await wrapper.get('form').trigger('submit')
        await flushPromises()
        expect(JSON.parse(fetcher.mock.calls[0]?.[1]?.body as string)).toEqual({
            email: 'user@example.test',
            password: 'long-password',
        })
        expect(session.context?.csrf_token).toBe('rotated')
        expect(router.currentRoute.value.path).toBe('/account')
        wrapper.unmount()
    })
    it('shows localized server errors without losing login email', async () => {
        session.lang = 'ru'
        vi.stubGlobal(
            'fetch',
            vi.fn(async () =>
                response({ error: 'Неверный адрес или пароль.' }, 400),
            ),
        )
        const { wrapper } = await setup(Auth, '/login?lang=ru')
        await wrapper.get('#email').setValue('person@example.test')
        await wrapper.get('form').trigger('submit')
        await flushPromises()
        expect(wrapper.get('[role="alert"]').text()).toBe(
            'Неверный адрес или пароль.',
        )
        expect(wrapper.get<HTMLInputElement>('#email').element.value).toBe(
            'person@example.test',
        )
        expect(wrapper.text()).toContain('Войти')
        wrapper.unmount()
    })
    it('loads requested list pagination and refreshes after a mark changes', async () => {
        const fetcher = vi.fn(async (url: unknown) =>
            String(url).includes('/account/marks')
                ? response({ marks: {} })
                : response({
                      lists: [
                          {
                              flag: 'watched',
                              label: 'Watched',
                              page: 2,
                              total: 41,
                              has_next: true,
                              movies: [
                                  {
                                      movie,
                                      mark: {
                                          movie_id: movie.id,
                                          watched: true,
                                          liked: false,
                                          watchlist: false,
                                      },
                                  },
                              ],
                          },
                      ],
                      marks: {},
                  }),
        )
        vi.stubGlobal('fetch', fetcher)
        const { wrapper } = await setup(
            Account,
            '/account?list=watched&page=2&lang=en',
        )
        expect(String(fetcher.mock.calls[0]?.[0])).toContain('page=2')
        expect(wrapper.text()).toContain('Page 2')
        await wrapper.findAll('.movie-marks button')[0]!.trigger('click')
        await flushPromises()
        expect(fetcher).toHaveBeenCalledTimes(3)
        expect(wrapper.get('.pagination a').attributes('href')).toContain(
            'page=1',
        )
        wrapper.unmount()
    })
    it('keeps account cards during delayed refreshes and localized failures, ignoring stale responses', async () => {
        const list: MovieList = {
            flag: 'watched', label: 'Watched', page: 1, total: 2,
            has_next: true,
            movies: [{ movie, mark: { movie_id: movie.id, watched: true, liked: false, watchlist: false } }],
        }
        const pending: ((value: Response) => void)[] = []
        let initial = true
        vi.stubGlobal('fetch', vi.fn((url: unknown) => {
            if (String(url).includes('/account/marks')) return Promise.resolve(response({ marks: {} }))
            if (initial) {
                initial = false
                return Promise.resolve(response({ lists: [list], marks: {} }))
            }
            return new Promise<Response>(resolve => pending.push(resolve))
        }))
        const { wrapper, router } = await setup(Account, '/account?lang=en')
        const card = wrapper.get('article').element
        await wrapper.get('.movie-marks button').trigger('click')
        await flushPromises()
        expect(wrapper.get('[role="status"]').text()).toBe('Loading…')
        expect(wrapper.get('article').element).toBe(card)
        await router.push('/account?list=watched&page=2&lang=en')
        await flushPromises()
        pending[1]!(response({ error: 'Не удалось обновить списки.' }, 503))
        await flushPromises()
        expect(wrapper.get('[role="alert"]').text()).toBe('Не удалось обновить списки.')
        expect(wrapper.get('article').element).toBe(card)
        pending[0]!(response({ lists: [], marks: {} }))
        await flushPromises()
        expect(wrapper.get('article').element).toBe(card)
        expect(wrapper.find('[role="status"]').exists()).toBe(false)
        await router.push('/account?lang=en')
        await flushPromises()
        expect(wrapper.get('article').element).toBe(card)
        pending[2]!(response({ lists: [{ ...list, total: 0, has_next: false, movies: [] }], marks: {} }))
        await flushPromises()
        expect(wrapper.find('article').exists()).toBe(false)
        expect(wrapper.text()).toContain('Watched (0)')
        expect(wrapper.text()).toContain('No movies in this list yet.')
        wrapper.unmount()
    })

})

describe('external search queue', () => {
    it('releases the form after 202 and permits a subsequent local search', async () => {
        const fetcher = vi.fn(async (_url: unknown, options?: RequestInit) => {
            if (options?.method === 'POST') {
                const params = JSON.parse(options.body as string)
                return params.q === '1' ? response({ token: 'local' }) : response({ task_id: 'task', status: 'queued' }, 202)
            }
            return response({ result: { messages: [], groups: [] }, marks: {} })
        })
        vi.stubGlobal('fetch', fetcher)
        const { wrapper, router } = await setup(Search, '/?lang=en')
        await wrapper.get('#query').setValue('external')
        await wrapper.get('form').trigger('submit')
        await flushPromises()
        expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
        expect(router.currentRoute.value.query.result).toBeUndefined()
        expect(searchTasks.tasks).toHaveLength(1)
        await wrapper.get('#query').setValue('1')
        await wrapper.get('form').trigger('submit')
        await flushPromises()
        expect(router.currentRoute.value.query.result).toBe('local')
        expect(searchTasks.tasks).toHaveLength(1)
        wrapper.unmount()
    })
    it('renders the occupied task link from structured 409 responses', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => response({
            code: 'external_search_in_progress', task_id: 'active-task', error: 'Внешний поиск уже выполняется.',
        }, 409)))
        session.lang = 'ru'
        const { wrapper } = await setup(Search, '/?lang=ru')
        await wrapper.get('#query').setValue('another external movie')
        await wrapper.get('form').trigger('submit')
        await flushPromises()
        expect(wrapper.get('[role="alert"]').text()).toContain('Внешний поиск уже выполняется.')
        expect(wrapper.get('[role="alert"] a').attributes('href')).toContain('task=active-task')
        expect(wrapper.get('[role="alert"] a').text()).toBe('Открыть задачу поиска')
        expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
        wrapper.unmount()
    })
})
