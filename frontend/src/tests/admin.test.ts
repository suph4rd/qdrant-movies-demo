// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AdminUsers from '../pages/AdminUsers.vue'
import AdminUser from '../pages/AdminUser.vue'
import { api } from '../api'
import { session } from '../session'
import type { User } from '../types'

vi.mock('../api', () => ({ api: vi.fn() }))
vi.mock('../session', async () => {
  const { reactive } = await import('vue')
  return { session: reactive({ context: null, lang: 'en' }) }
})
vi.mock('../i18n', () => ({ t: (value: string) => value }))

const actor: User = { id: 1, email: 'admin@example.com', role: 'admin', blocked: false, created_at: '2026-01-01T00:00:00Z', deleted_at: null }
const target: User = { ...actor, id: 2, email: 'movie@example.com', role: 'user' }
const response = (user: User = target) => ({ user, lists: [{ flag: 'watched', label: 'Watched', page: 1, total: 0, has_next: false, movies: [] }], page: 1, has_next: false })
const mockedApi = vi.mocked(api)

async function page(path: string) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/admin/users', component: AdminUsers },
    { path: '/admin/users/:id', component: AdminUser },
  ] })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(path.match(/users\/\d/) ? AdminUser : AdminUsers, { global: { plugins: [router] } })
  return { wrapper, router }
}

beforeEach(() => {
  vi.clearAllMocks()
  session.context = { user: actor } as typeof session.context
  session.lang = 'en'
})

describe('administrator users', () => {
  it('shows loading while users are requested', async () => {
    mockedApi.mockReturnValueOnce(new Promise(() => {}))
    const { wrapper } = await page('/admin/users')
    expect(wrapper.get('[role="status"]').text()).toBe('Loading…')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('keeps filters and pagination in the URL and sends them to the API', async () => {
    mockedApi.mockResolvedValue({ users: [target], has_next: true, page: 2 })
    const { wrapper, router } = await page('/admin/users?q=movie&role=user&state=active&page=2')
    await flushPromises()
    expect(mockedApi).toHaveBeenLastCalledWith('/admin/users', { query: { q: 'movie', role: 'user', state: 'active', page: '2' } })
    expect(wrapper.text()).toContain('movie@example.com')
    expect(wrapper.findAll('a').find(link => link.text() === 'Next')?.attributes('href')).toContain('page=3')
    await wrapper.get('#email-search').setValue('another')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'another', role: 'user', state: 'active', lang: 'en' })
    wrapper.unmount()
  })

  it('shows API failures instead of an empty users result', async () => {
    mockedApi.mockRejectedValueOnce(new Error('Administrator access required'))
    const { wrapper } = await page('/admin/users')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('Administrator access required')
    expect(wrapper.text()).not.toContain('No users found.')
    wrapper.unmount()
  })

  it('does not request protected data for a regular user', async () => {
    session.context = { user: target } as typeof session.context
    const { wrapper } = await page('/admin/users')
    await flushPromises()
    expect(mockedApi).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toBe('Administrator access required')
    wrapper.unmount()
  })
})

describe('administrator user actions', () => {
  it('submits block once, disables actions, and reloads the updated user', async () => {
    let finish!: (value: unknown) => void
    mockedApi.mockResolvedValueOnce(response())
    const { wrapper } = await page('/admin/users/2')
    await flushPromises()
    mockedApi.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    mockedApi.mockResolvedValueOnce(response({ ...target, blocked: true }))
    const block = wrapper.findAll('button').find(button => button.text() === 'Block')!
    await block.trigger('click')
    await block.trigger('click')
    expect(mockedApi.mock.calls.filter(call => call[1]?.method === 'POST')).toHaveLength(1)
    expect(mockedApi).toHaveBeenLastCalledWith('/admin/users/2', { method: 'POST', body: { action: 'block', confirmation_email: '' } })
    expect(block.attributes('disabled')).toBeDefined()
    finish({ ok: true })
    await flushPromises()
    expect(wrapper.text()).toContain('Unblock')
    wrapper.unmount()
  })

  it('preserves email confirmation when sending deletion and displays rejected actions', async () => {
    mockedApi.mockResolvedValueOnce(response())
    const { wrapper } = await page('/admin/users/2')
    await flushPromises()
    const input = wrapper.get('#confirmation-email')
    expect(input.attributes('required')).toBeDefined()
    await input.setValue('movie@example.com')
    mockedApi.mockRejectedValueOnce(new Error('The last active administrator must be preserved.'))
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(mockedApi).toHaveBeenLastCalledWith('/admin/users/2', { method: 'POST', body: { action: 'delete', confirmation_email: 'movie@example.com' } })
    expect(wrapper.get('[role="alert"]').text()).toBe('The last active administrator must be preserved.')
    wrapper.unmount()
  })

  it('hides self block, delete and demote actions', async () => {
    mockedApi.mockResolvedValueOnce(response(actor))
    const { wrapper } = await page('/admin/users/1')
    await flushPromises()
    expect(wrapper.findAll('button')).toHaveLength(0)
    expect(wrapper.find('#confirmation-email').exists()).toBe(false)
    wrapper.unmount()
  })

  it('offers only restore for a deleted user and keeps movie lists read-only', async () => {
    mockedApi.mockResolvedValueOnce(response({ ...target, deleted_at: '2026-01-02T00:00:00Z' }))
    const { wrapper } = await page('/admin/users/2')
    await flushPromises()
    expect(wrapper.findAll('button').map(button => button.text())).toEqual(['Restore as blocked'])
    expect(wrapper.text()).toContain('Movie lists are read-only for administrators.')
    wrapper.unmount()
  })
})
