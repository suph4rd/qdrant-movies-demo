# JSON API contract

All endpoints use `/api`, same-origin cookies, `?lang=en|ru`, and JSON. Mutations require `X-CSRF-Token` from context; Origin must match. Errors: `{error: string}` with 400 validation/domain, 401 unauthenticated, 403 forbidden, 404 missing, 409 duplicate email, 422 malformed input. All movie IDs are decimal strings, including nested payloads. Unexpected errors propagate as 500.

- GET `/context`: `{user: User|null, lang, csrf_token, catalog: Movie[], search_modes: string[], limit_options: string[], default_mode, default_limit, movie_count: number|null, marks: Record<string,Mark>}`. Sets CSRF/language cookie.
- POST `/search` body `{q,mode,limit}` (all strings): `{token: string}`. Executes import once and stores result/error.
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
