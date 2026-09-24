# uniqyou's Instagram Post Review Tool (V1)

**Live app:** https://uniqyou-trends-bzi3mwc43s4ejtefz4q4qe.streamlit.app/

A small internal Streamlit app. Paste an Instagram post URL and the app resolves
it through Meta's official Instagram oEmbed API, saves it, and shows the post so
people can upvote it and comment on it. The live app stores data in Supabase
(Postgres), and local runs default to a SQLite file.

```
Streamlit UI (app.py, ui/)
      │
      ▼
Service layer (services/)  ──────►  SQLAlchemy (database/): Supabase Postgres or local SQLite
      │
      ▼
InstagramClient (instagram/client.py)
      │
      ▼
Meta Instagram oEmbed API
```

The UI only calls services. Only `instagram/client.py` talks to Meta. If the
integration changes, swap the `InstagramClient` implementation and its settings;
the database, votes, comments and UI stay the same.

## Requirements

- Python 3.11 or newer (developed on 3.12)
- Internet access to `graph.facebook.com` and `www.instagram.com`
- Optional: a Meta app token for higher rate limits (see below)

## Installation

```bash
cd instagram-review-tool
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional; the app runs without a token
streamlit run app.py
```

The app opens at http://localhost:8501.

## Instagram/Meta API configuration

The app uses Meta's **Instagram oEmbed** endpoint:

```
GET https://graph.facebook.com/{META_GRAPH_API_VERSION}/instagram_oembed?url=<post url>[&access_token=<token>]
```

**No token (default).** Since June 15, 2026, Meta serves oEmbed for public
Instagram posts without an access token, and no App Review is needed. Meta's
own WordPress plugin works this way. Leave `INSTAGRAM_ACCESS_TOKEN` unset and
the app calls the endpoint tokenless. Rate limits are lower in this mode.

**With a token (optional, for higher limits).** This needs a *Facebook-login*
Meta app. The "API setup with Instagram login" product and its **Instagram app
ID/secret** do not work for oEmbed.

1. In https://developers.facebook.com/apps, open or create an app, then
   *Add use case* → the embed use case (the **oEmbed Read** feature). The
   token-based route may still require Business Verification and App Review.
   Check https://developers.facebook.com/docs/instagram-platform/oembed.
2. Copy the **App ID** from *App settings → Basic*. This is the Meta app ID,
   not the Instagram app ID.
3. Copy the **Client token** from *App settings → Advanced → Security*.
4. Put them in `.env` as `APP_ID|CLIENT_TOKEN`:

   ```
   INSTAGRAM_ACCESS_TOKEN=1234567890|abcdef...
   META_GRAPH_API_VERSION=v25.0
   ```

   Or put the same keys in `.streamlit/secrets.toml`. Environment variables take
   precedence.

**Automatic fallback.** When a token is set, the app tries it first. If Meta
rejects it with an auth or permission error, the app retries the same request
tokenless and stops sending the token until the app restarts. The usual cause is
that *Meta oEmbed Read* hasn't passed App Review, which Meta reports as error
code 10. A configured but unapproved token therefore never breaks adding posts.

`.env` and `.streamlit/secrets.toml` are git-ignored. The token is never shown in
the UI or written to logs.

### Public vs private posts

oEmbed only returns posts that are public and embeddable. When Meta refuses a
URL, the app shows:

> This post is from a private account (or is no longer public), so we can't show the image.

Meta returns the same error for private accounts, deleted posts and posts whose
owner turned off embedding. The app can't tell these apart, so the message
covers all three. Nothing is saved when a post can't be retrieved.

## SQLite configuration

By default the database is created at `data/instagram_review.db`, along with its
tables, the first time the app starts (`init_db()`). You don't need to create
anything by hand. To use a different location, set:

```
DATABASE_URL=sqlite:////absolute/path/to/instagram_review.db
```

### Postgres / Supabase (needed for Streamlit Cloud)

Streamlit Cloud deletes local files when the app restarts, so the SQLite file
won't survive there. Point `DATABASE_URL` at a Supabase Postgres database
instead. Use the **Session pooler** string (Supabase → *Connect* → *Session
pooler*), because Streamlit Cloud can't reach the IPv6-only direct connection:

```
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

The app switches to the psycopg driver, requires TLS, and creates the tables on
first start. It also turns on row-level security so Supabase's public REST API
can't read or write them. On Streamlit Cloud, put `DATABASE_URL` in *App
settings → Secrets*.

Tables: `posts`, `comments`, `upvotes`. Vote and comment counts are computed
with `COUNT(*)` on their tables. Deleting a post cascades to its comments and
votes. `posts` has one column beyond the V1 spec: `embed_html`. See the
limitations section for why.

## Running tests

```bash
pytest
```

The tests use a temporary SQLite file per test. They replace the Instagram API
with fakes, so no real Instagram calls are made. They cover URL validation,
post creation, duplicate prevention, upvotes, comments (including empty
comments), database initialization and restart persistence, and how Meta error
responses are handled.

## What the app does

- **Add Post**: trims and validates the URL (HTTPS, instagram.com host, a
  `/p/`, `/reel/` or `/tv/` post path), then normalizes it to
  `https://www.instagram.com/<type>/<code>/`. Tracking parameters like `?igsh=`
  are dropped, so one post shared different ways is stored once.
- **Duplicate**: shows *"This Instagram post has already been added."* and
  displays the existing post. Instagram isn't called again.
- **Upvote**: every click adds one row to `upvotes`. There are no users in V1,
  so votes aren't limited per person.
- **Comments**: blank comments are rejected. Comments are trimmed, stored, and
  shown oldest first.
- **Layout**: a red and black theme. The first screen shows only the title,
  the link box and *Add post*. Saved posts sit below it in a grid.
- **Post popup**: *Add post* opens a popup with the post, *Upvote*, a link to
  Instagram, the comments and a comment box. *Open* on any saved card opens the
  same popup.
- **Errors**: invalid URL, duplicate, auth failure, rate limit, unavailable or
  private post, and database errors each show a user-friendly message. Technical
  details are logged on the server only.

## Known Instagram API limitations

- **No direct image URL.** Meta removed `thumbnail_url` (along with
  `author_name` and `title`) from oEmbed responses. The API now returns only the
  official embed `html`. The app stores that HTML in `posts.embed_html` as proof
  the post was embeddable when it was added. For display it does not run the
  stored HTML. Instead it builds Instagram's standard embed markup from the
  validated post URL, and Instagram's `embed.js` draws the image. This matters
  because `st.iframe` runs HTML strings with scripts and the app's own origin. If Meta ever returns `thumbnail_url` again, the client saves
  it as `media_url` and the app shows it with `st.image`.
- **Rendering needs instagram.com.** The browser must be able to load
  `https://www.instagram.com/embed.js`. Stored embeds can stop rendering if the
  owner later deletes the post, makes it private or turns off embedding.
- **Captions aren't returned** as a separate field, so `posts.caption` is usually
  empty. The caption appears inside the embed.
- **Public posts only.** The app can't retrieve posts from private accounts,
  age-restricted content, or Stories.
- **Rate limits.** Tokenless calls get lower limits than token calls. Every new
  URL uses one call, and known URLs are served from SQLite.
- **Terms of use.** oEmbed is meant for embedding. Displaying Instagram content
  must follow Meta's Platform Terms.

## Project layout

```
app.py                  Streamlit entry point
config.py               Settings from env / .env / Streamlit secrets
database/db.py          Engine, sessions, init_db()
database/models.py      Post, Comment, Upvote
instagram/client.py     InstagramClient interface + Meta oEmbed implementation
instagram/exceptions.py Integration errors with user-safe messages
services/               Posts, comments, votes, URL validation, service errors
ui/                     Landing form, post cards, popup, red/black theme (theme.py)
.streamlit/config.toml  Streamlit theme colors
tests/                  pytest suite
```
