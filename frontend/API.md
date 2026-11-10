# JSON API contract

All endpoints use `/api`, same-origin cookies, `?lang=en|ru`, and JSON. Mutations require `X-CSRF-Token` from context; Origin must match. Errors: `{error: string}` with 400 validation/domain, 401 unauthenticated, 403 forbidden, 404 missing, 409 duplicate email or occupied external search slot, 422 malformed input. All movie IDs are decimal strings, including nested payloads. Unexpected errors propagate as 500.

- GET `/context`: `{user: User|null, lang, csrf_token, catalog: Movie[], search_modes: string[], limit_options: string[], default_mode, default_limit, movie_count: number|null, marks: Record<string,Mark>}`. Sets CSRF/language cookies and a random HttpOnly `movie_search_guest` cookie (one-year lifetime); only its hash identifies a guest in PostgreSQL.
- POST `/search` body `{q,mode,limit}` (all strings): saved movie and description searches return `200 {token:string}` with a synchronous result/error snapshot. When an external lookup is needed, returns `202 {task_id:string,status:"queued"|"running"}`. A repeated active request with the same trimmed query, mode and limit returns the same task with 202. A different external request returns `409 {code:"external_search_in_progress",task_id:string,status,error:string}`. Saved movie lookup always precedes this limit; numeric IDs never trigger external lookup.
- GET `/search?q=...&mode=movie&limit=10&result=token`: `{result: {groups:[{source:Movie|null,recommendations:[{id:string,score:number,payload:Movie}]}],messages:string[]}|null, marks: Record<string,Mark>, movie_count:number|null}`. Reads cache or searches without import.
- POST `/register` `{email,password,password_repeat}`, POST `/login` `{email,password}`, POST `/logout` `{}`: fresh context with rotated CSRF and auth cookies.
- GET `/account?list=watched&page=1`: `{lists: MovieList[], marks:Record<string,Mark>}`.
- POST `/account/marks` `{movie_id:string,flag:watched|liked|watchlist,state:boolean,reference:string}`: `{marks:Record<string,Mark>}`.
- GET `/admin/users?q=&role=&state=&page=1`: `{users:User[],has_next:boolean,page:number}`.
- GET `/admin/users/:id?page=1`: `{user:User,lists:MovieList[],page:number,has_next:boolean}`.
- POST `/admin/users/:id` `{action,confirmation_email}`: `{ok:true}`.

User: `{id:number,email,role,blocked,created_at:string,deleted_at:string|null}`.
Movie: `{id:string,title,year,genres:string[],description,original_title?,wikidata_id?,tmdb_id?,description_language?,mark_reference?}`. Imported mark references are issued only for verified cards, and must be preserved.
Mark: `{movie_id:string,watched:boolean,liked:boolean,watchlist:boolean}`.
MovieList: `{flag,label,page,total,has_next,movies:[{movie:Movie,mark:Mark}]}`. Three lists are returned; only selected list uses requested page on account. Admin paginates all lists together. Labels and movie content are localized.

## Durable external search tasks

- GET `/search-tasks`: `{tasks:SearchTask[]}` containing the owner's active tasks and unread completions, ordered by creation time and ID.
- GET `/search-tasks/{task_id}`: `{task:SearchTask & {result:SearchResult|null,error:string|null},marks:Record<string,Mark>,movie_count:number|null}`. Localizes stored results/errors at read time and issues fresh verified card references for authenticated users. Unknown or foreign task IDs return 404. Completed tasks remain accessible after acknowledgement.
- POST `/search-tasks/{task_id}/read` `{}`: `{ok:true}`; requires CSRF and matching Origin. Acknowledges terminal tasks only, with no effect on the active search slot.
- WebSocket `/notifications/ws`: requires a same-origin Origin header and session/guest cookies. Sends `{event:"search.completed",task_id,status:"succeeded"|"failed"}` once per unread task per connection, and `{event:"heartbeat"}` every 15 seconds. Checks the current identity and its completions once per second. Foreign/missing Origin closes with 1008. Reconnecting replays unread completions; clients deduplicate by `task_id` and restore the task list on reconnect. Events contain no movie data; fetch task details to render results.

SearchTask: `{task_id:string,status:"queued"|"running"|"succeeded"|"failed",params:{q,mode,limit},created_at:string,completed_at:string|null,read:boolean}`. SearchResult has the same shape as the `result` of GET `/search`.

An account has one active external task across browsers/backend processes. Guests have one per browser cookie. After login, new tasks belong to the account; any active task from this browser's guest cookie also blocks new external tasks. Only identities visible in the current session can list, read or acknowledge tasks. Logging out removes access to account tasks, while guest tasks remain accessible through the guest cookie.

Task/outbox creation is atomic in PostgreSQL. The slot is retained through backend/worker/browser restarts and Kafka outages, and released atomically with `succeeded` or `failed`. There is no automatic cancellation, deletion or retry of completed errors. Opening a task result acknowledges its completion; notifications never navigate automatically.
