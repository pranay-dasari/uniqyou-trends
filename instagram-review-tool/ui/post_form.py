"""The first screen: title, "paste link" box and Add post button."""

from __future__ import annotations

import logging

import streamlit as st

from instagram.exceptions import InstagramError
from services.errors import ServiceError
from services.post_service import create_post

logger = logging.getLogger(__name__)

# Read by app.py after the page renders, to open the post popup.
OPEN_POST_KEY = "open_post"
FLASH_KEY = "post_form_flash"


def render_post_form(has_posts: bool) -> None:
    with st.container(key="hero"):
        st.html(
            '<div class="hero-icon"></div>'
            '<p class="hero-title">uniqyou\'s <span>Instagram</span> Post Review Tool</p>'
            '<p class="hero-sub">Paste a public Instagram post or reel link</p>'
        )
        with st.form("add_post_form", clear_on_submit=False, border=False):
            url_col, button_col = st.columns([5, 1], vertical_alignment="bottom")
            with url_col:
                url = st.text_input(
                    "Paste Instagram Post URL",
                    placeholder="https://www.instagram.com/p/…",
                    key="new_post_url",
                    label_visibility="collapsed",
                )
            with button_col:
                submitted = st.form_submit_button("Add post", type="primary", width="stretch")

        if submitted:
            _handle_submit(url)

        if message := st.session_state.pop(FLASH_KEY, None):
            st.error(message)

        if has_posts:
            st.html('<p class="scroll-hint">⌄ Scroll for saved posts</p>')


def _handle_submit(url: str) -> None:
    try:
        with st.spinner("Retrieving post from Instagram…"):
            result = create_post(url)
    except (InstagramError, ServiceError) as exc:
        st.session_state[FLASH_KEY] = exc.user_message
        return
    except Exception:
        logger.exception("Unexpected error while adding a post")
        st.session_state[FLASH_KEY] = ServiceError.user_message
        return

    status = "Post added" if result.created else "This Instagram post has already been added."
    st.session_state[OPEN_POST_KEY] = (result.post.id, status)
