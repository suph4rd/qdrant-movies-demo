import { expect, test, type Page } from '@playwright/test'
import type { Context, Mark, Movie, User } from '../src/types'

const actor: User = { id: 1, email: 'admin@example.com', role: 'admin', blocked: false, created_at: '2026-01-01T00:00:00Z', deleted_at: null }
const target: User = { ...actor, id: 2, email: 'viewer@example.com', role: 'user' }
const movieId = '18446744073709551614'
const movie: Movie = { id: movieId, title: 'A distant planet', year: 2026, genres: ['Science fiction'], description: 'An expedition discovers a distant world.', wikidata_id: 'Q123', mark_reference: 'verified-card' }

type Call = { path: string; method: string; body: Record<string, unknown> | null; query: URLSearchParams; csrf: string | undefined }
async function mockApi(page: Page, user: User | null = null) {
  const state = { user, csrf: 'initial-csrf', marks: {} as Record<string, Mark>, calls: [] as Call[], error: '', delaySearch: false, blocked: false }
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname.slice(4), method = request.method()
    const body = request.postDataJSON() as Record<string, unknown> | null
    state.calls.push({ path, method, body, query: url.searchParams, csrf: request.headers()['x-csrf-token'] })
    const ru = url.searchParams.get('lang') === 'ru'
    const shownMovie = { ...movie, title: ru ? 'Далёкая планета' : movie.title }
    const context = (): Context => ({ user: state.user, lang: ru ? 'ru' : 'en', csrf_token: state.csrf, catalog: [shownMovie], search_modes: ['movie', 'description'], limit_options: ['5', '10', '20', '50'], default_mode: 'movie', default_limit: '10', movie_count: 251, marks: state.marks })
    const respond = (json: unknown, status = 200) => route.fulfill({ status, json })
    if (path === '/context') return respond(context())
    if (path === '/login' || path === '/register') {
      if (state.error) return respond({ error: state.error }, 400)
      state.user = { ...actor, role: 'user', email: String(body?.email) }
      state.csrf = `${path.slice(1)}-csrf`
      return respond(context())
    }
    if (path === '/logout') { state.user = null; state.csrf = 'logout-csrf'; return respond(context()) }
    if (path === '/search' && method === 'POST') {
      if (state.delaySearch) await new Promise(resolve => setTimeout(resolve, 200))
      return respond({ token: `saved-${body?.q}` })
    }
    if (path === '/search') {
      if (state.error) return respond({ error: state.error }, 400)
      return respond({ result: { messages: [], groups: [{ source: null, recommendations: [{ id: movieId, score: .93, payload: shownMovie }] }] }, marks: state.marks })
    }
    if (path === '/account/marks') {
      const flag = String(body?.flag) as 'watched' | 'liked' | 'watchlist'
      const mark = state.marks[movieId] || { movie_id: movieId, watched: false, liked: false, watchlist: false }
      mark[flag] = Boolean(body?.state)
      if (mark[flag] && flag === 'watched') mark.watchlist = false
      if (mark[flag] && flag === 'watchlist') mark.watched = false
      state.marks[movieId] = mark
      return respond({ marks: state.marks })
    }
    if (path === '/account') {
      if (!state.user) return respond({ error: 'Authentication required' }, 401)
      return respond({ marks: state.marks, lists: (['watched', 'liked', 'watchlist'] as const).map(flag => {
        const marked = state.marks[movieId]?.[flag]
        return { flag, label: flag === 'watchlist' ? 'Watchlist' : flag === 'liked' ? 'Liked' : 'Watched', page: Number(url.searchParams.get('page') || 1), total: marked ? 1 : 0, has_next: false, movies: marked ? [{ movie: shownMovie, mark: state.marks[movieId] }] : [] }
      }) })
    }
    if (path === '/admin/users') return respond({ users: [target], page: Number(url.searchParams.get('page') || 1), has_next: url.searchParams.get('page') !== '2' })
    if (path === '/admin/users/2' && method === 'POST') {
      if (body?.action === 'delete' && body?.confirmation_email !== target.email) return respond({ error: 'The confirmation email does not match.' }, 400)
      state.blocked = body?.action === 'block'
      return respond({ ok: true })
    }
    if (path === '/admin/users/2') return respond({ user: { ...target, blocked: state.blocked }, lists: [], page: 1, has_next: false })
    return respond({ error: 'Not found' }, 404)
  })
  return state
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
}

test('search keeps cached tokens through history, reload and language changes', async ({ page }) => {
  const state = await mockApi(page)
  state.delaySearch = true
  await page.goto('/?lang=en')
  await page.getByLabel('Movie title, ID, or description').fill('first')
  await page.getByRole('button', { name: 'Find similar movies' }).click()
  await expect(page.getByRole('button', { name: 'Find similar movies' })).toBeDisabled()
  await expect(page.getByRole('heading', { name: movie.title })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Source: Wikidata' })).toHaveAttribute('href', 'https://www.wikidata.org/wiki/Q123')
  await expect(page).toHaveURL(/result=saved-first/)
  await page.getByLabel('Movie title, ID, or description').fill('second')
  await page.getByRole('button', { name: 'Find similar movies' }).click()
  await expect(page).toHaveURL(/result=saved-second/)
  await page.goBack()
  await expect(page.getByLabel('Movie title, ID, or description')).toHaveValue('first')
  await page.goForward()
  await expect(page.getByLabel('Movie title, ID, or description')).toHaveValue('second')
  await page.getByRole('link', { name: 'RU', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Далёкая планета' })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('lang', 'ru')
  await expect(page).toHaveURL(/result=saved-second/)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Далёкая планета' })).toBeVisible()
  expect(state.calls.filter(call => call.path === '/search' && call.method === 'POST')).toHaveLength(2)
  expect(state.calls.filter(call => call.path === '/search' && call.method === 'GET').every(call => call.query.get('result')?.startsWith('saved-'))).toBe(true)
  await noOverflow(page)
})

test('registration rotates the token; marks preserve large IDs and update account lists', async ({ page }) => {
  const state = await mockApi(page)
  await page.goto('/register?lang=en')
  await page.getByLabel('Email', { exact: true }).fill('new@example.com')
  await page.getByLabel('Password', { exact: true }).fill('strong-password-123')
  await page.getByLabel('Repeat password').fill('strong-password-123')
  await page.getByRole('button', { name: 'Register', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'My account' })).toBeVisible()
  await page.goto('/?q=planet&mode=movie&limit=10&result=saved-planet&lang=en')
  await page.getByRole('button', { name: 'Add to Watchlist', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Remove from Watchlist', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Add to Watched', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Add to Watchlist', exact: true })).toHaveAttribute('aria-pressed', 'false')
  const markCalls = state.calls.filter(call => call.path === '/account/marks')
  expect(markCalls).toHaveLength(2)
  expect(markCalls[0].body).toEqual({ movie_id: movieId, flag: 'watchlist', state: true, reference: 'verified-card' })
  expect(markCalls.every(call => call.csrf === 'register-csrf')).toBe(true)
  await page.getByRole('link', { name: 'Account', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Watched (1)', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: movie.title })).toBeVisible()
  await page.getByRole('button', { name: 'Remove from Watched', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Watched (0)', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Log out', exact: true }).click()
  await expect(page.getByRole('link', { name: 'Log in', exact: true })).toBeVisible()
  expect(state.calls.find(call => call.path === '/logout')?.csrf).toBe('register-csrf')
  await noOverflow(page)
})

test('login failures remain visible and successful login updates navigation', async ({ page }) => {
  const state = await mockApi(page)
  state.error = 'Invalid email or password.'
  await page.goto('/login?lang=en')
  await page.getByLabel('Email', { exact: true }).fill('viewer@example.com')
  await page.getByLabel('Password', { exact: true }).fill('strong-password-123')
  await page.getByRole('button', { name: 'Log in', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Invalid email or password.')
  state.error = ''
  await page.getByRole('button', { name: 'Log in', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'My account' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Users', exact: true })).toHaveCount(0)
})

test('administrator filters and pagination survive direct navigation; action reloads detail', async ({ page }) => {
  const state = await mockApi(page, actor)
  await page.goto('/admin/users?q=viewer&role=user&state=active&lang=en')
  await expect(page.getByLabel('Search email')).toHaveValue('viewer')
  await expect(page.getByRole('link', { name: target.email })).toBeVisible()
  await page.getByRole('link', { name: 'Next', exact: true }).click()
  await expect(page).toHaveURL(/page=2/)
  await expect(page.getByRole('link', { name: 'Next', exact: true })).toHaveCount(0)
  await page.reload()
  await expect(page.getByLabel('Search email')).toHaveValue('viewer')
  expect(state.calls.filter(call => call.path === '/admin/users').at(-1)?.query.get('page')).toBe('2')
  await page.getByLabel('Search email').fill('other')
  await page.getByLabel('Role', { exact: true }).selectOption('admin')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page).toHaveURL(/q=other/)
  await expect(page).toHaveURL(/role=admin/)
  await expect(page).not.toHaveURL(/page=2/)
  await page.getByRole('link', { name: target.email }).click()
  await expect(page.getByRole('heading', { name: target.email })).toBeVisible()
  await page.getByRole('button', { name: 'Block', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Unblock', exact: true })).toBeVisible()
  await page.getByLabel('Confirm deletion by entering the user email.').fill('wrong@example.com')
  await page.getByRole('button', { name: 'Delete user', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('The confirmation email does not match.')
  const action = state.calls.find(call => call.body?.action === 'block')
  expect(action?.csrf).toBe('initial-csrf')
  await noOverflow(page)
})

test('restricted admin page and search failure render explicit errors', async ({ page }) => {
  const state = await mockApi(page, { ...actor, role: 'user' })
  await page.goto('/admin/users?lang=en')
  await expect(page.getByRole('alert')).toHaveText('Administrator access required')
  expect(state.calls.some(call => call.path === '/admin/users')).toBe(false)
  state.error = 'Search is temporarily unavailable.'
  await page.goto('/?q=planet&mode=movie&limit=10&lang=en')
  await expect(page.getByRole('alert')).toHaveText('Search is temporarily unavailable.')
  await expect(page.getByRole('heading', { name: movie.title })).toHaveCount(0)
})

async function longAccount(page: Page) {
  await mockApi(page, target)
  const state = { marks: {} as Record<string, Mark>, emptyWatchlist: false, pending: null as (() => void) | null, defer: false }
  await page.route('**/api/account?*', async route => {
    if (state.defer) await new Promise<void>(resolve => { state.pending = resolve })
    const pageNumber = Number(new URL(route.request().url()).searchParams.get('page') || 1)
    const watched = Array.from({ length: 12 }, (_, index) => {
      const id = String(pageNumber * 100 + index)
      return { movie: { ...movie, id, title: `Movie ${id}` }, mark: { movie_id: id, watched: true, liked: state.marks[id]?.liked || false, watchlist: false } }
    })
    const last = { movie: { ...movie, id: 'last', title: 'Last watchlist movie' }, mark: { movie_id: 'last', watched: false, liked: false, watchlist: true } }
    const marks = Object.fromEntries([...watched, ...(state.emptyWatchlist ? [] : [last])].map(entry => [entry.movie.id, entry.mark]))
    state.marks = marks
    await route.fulfill({ json: { marks, lists: [
      { flag: 'watched', label: 'Watched', page: pageNumber, total: 24, has_next: pageNumber === 1, movies: watched },
      { flag: 'liked', label: 'Liked', page: 1, total: 0, has_next: false, movies: [] },
      { flag: 'watchlist', label: 'Watchlist', page: 1, total: state.emptyWatchlist ? 0 : 1, has_next: false, movies: state.emptyWatchlist ? [] : [last] },
    ] } })
  })
  await page.route('**/api/account/marks?*', async route => {
    const body = route.request().postDataJSON()
    if (body.movie_id === 'last' && body.flag === 'watchlist') state.emptyWatchlist = true
    const mark = state.marks[body.movie_id]
    if (mark) mark[body.flag as 'watched' | 'liked' | 'watchlist'] = body.state
    await route.fulfill({ json: { marks: state.marks } })
  })
  await page.goto('/account?lang=en')
  await expect(page.getByRole('heading', { name: 'Movie 100', exact: true })).toBeVisible()
  return state
}

async function scrollY(page: Page) {
  return page.evaluate(() => window.scrollY)
}

test('account preserves scroll and cards during mark refresh and pagination, including history', async ({ page }) => {
  const state = await longAccount(page)
  const watched = page.getByRole('region', { name: 'Watched (24)', exact: true })
  const button = watched.locator('article').last().getByRole('button', { name: 'Add to Liked', exact: true })
  await button.evaluate(element => element.scrollIntoView({ block: 'center' }))
  const before = await scrollY(page)
  expect(before).toBeGreaterThan(500)
  state.pending = null
  state.defer = true
  await button.click()
  await expect(page.getByRole('status')).toHaveText('Loading…')
  await expect(watched.locator('article')).toHaveCount(12)
  expect(Math.abs(await scrollY(page) - before)).toBeLessThan(80)
  await expect.poll(() => state.pending !== null).toBe(true)
  state.defer = false
  state.pending!()
  await expect(page.getByRole('status')).toHaveCount(0)
  expect(Math.abs(await scrollY(page) - before)).toBeLessThan(80)

  const next = watched.getByRole('link', { name: 'Next', exact: true })
  await next.evaluate(element => element.scrollIntoView({ block: 'center' }))
  const beforePage = await scrollY(page)
  state.pending = null
  state.defer = true
  await next.click()
  await expect(page).toHaveURL(/page=2/)
  await expect(page.getByRole('status')).toHaveText('Loading…')
  await expect(page.getByRole('heading', { name: 'Movie 100', exact: true })).toHaveCount(1)
  expect(Math.abs(await scrollY(page) - beforePage)).toBeLessThan(80)
  await expect.poll(() => state.pending !== null).toBe(true)
  state.defer = false
  state.pending!()
  await expect(page.getByRole('heading', { name: 'Movie 200', exact: true })).toHaveCount(1)
  expect(Math.abs(await scrollY(page) - beforePage)).toBeLessThan(80)
  const pageTwoScroll = await scrollY(page)
  await page.evaluate(() => window.scrollTo(0, 600))
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Movie 100', exact: true })).toHaveCount(1)
  await expect.poll(() => scrollY(page)).toBeCloseTo(beforePage, -1)
  await page.goForward()
  await expect(page.getByRole('heading', { name: 'Movie 200', exact: true })).toHaveCount(1)
  await expect.poll(() => scrollY(page)).toBeCloseTo(600, -1)
  expect(pageTwoScroll).toBeGreaterThan(500)
  await page.getByRole('link', { name: 'Search', exact: true }).evaluate((element: HTMLAnchorElement) => element.click())
  await expect(page).toHaveURL('/?lang=en')
  await expect.poll(() => scrollY(page)).toBe(0)
  await noOverflow(page)
})

test('removing the last watchlist movie updates lists and clamps scroll to the shorter page', async ({ page }) => {
  await longAccount(page)
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
  const before = await scrollY(page)
  const watchlist = page.getByRole('region', { name: 'Watchlist (1)', exact: true })
  await watchlist.getByRole('button', { name: 'Remove from Watchlist', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Watchlist (0)', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Last watchlist movie', exact: true })).toHaveCount(0)
  await expect(page.getByRole('region', { name: 'Watchlist (0)', exact: true })).toContainText('No movies in this list yet.')
  await expect.poll(() => page.evaluate(() => Math.abs(window.scrollY - (document.documentElement.scrollHeight - window.innerHeight)))).toBeLessThan(3)
  expect(await scrollY(page)).toBeLessThan(before)
  expect(await scrollY(page)).toBeGreaterThan(500)
  await expect(page.getByRole('region', { name: 'Watched (24)', exact: true }).locator('article')).toHaveCount(12)
})
