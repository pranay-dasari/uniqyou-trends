"""uniqyou's Instagram Post Review Tool — Streamlit entry point.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import logging

import streamlit as st

from database.db import init_db
from services.errors import ServiceError
from services.post_service import list_posts
from ui.post_form import OPEN_POST_KEY, render_post_form
from ui.post_view import open_post_dialog, render_post_card
from ui.theme import apply_theme

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

GRID_COLUMNS = 3


@st.cache_resource
def _init_database() -> bool:
    init_db()
    return True


def main() -> None:
    st.set_page_config(
        page_title="uniqyou's Instagram Post Review Tool", page_icon="📷", layout="wide"
    )
    apply_theme()

    try:
        _init_database()
    except Exception:
        logger.exception("Database initialisation failed")
        st.error("The database could not be opened. Check the server logs.")
        st.stop()

    try:
        has_posts = bool(list_posts())
    except ServiceError as exc:
        st.error(exc.user_message)
        return

    # 1. First screen: title, link box, Add post.
    render_post_form(has_posts)

    # 3. Popup for a post that was just added (or already existed).
    if pending := st.session_state.pop(OPEN_POST_KEY, None):
        post_id, status = pending
        open_post_dialog(post_id, status)

    # 2. Saved posts, below the fold.
    try:
        posts = list_posts()
    except ServiceError as exc:
        st.error(exc.user_message)
        return
    if not posts:
        return

    st.html(f'<p class="section-title">Saved posts <span>· {len(posts)}</span></p>')
    with st.container(key="grid"):
        columns = st.columns(GRID_COLUMNS)
        for index, post in enumerate(posts):
            with columns[index % GRID_COLUMNS]:
                render_post_card(post, key_prefix="grid")


main()
