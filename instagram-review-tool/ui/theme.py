"""Red and black styling for the whole app (colors also set in .streamlit/config.toml)."""

from __future__ import annotations

import streamlit as st

RED = "#E24B4A"
RED_DARK = "#A32D2D"
BLACK = "#111111"
PANEL = "#1C1C1B"

_CSS = f"""
<style>
.stApp {{ background: {BLACK}; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1rem; }}

/* 1. First screen: title + link box + button, filling the viewport */
.st-key-hero {{
    min-height: calc(100vh - 4rem);
    justify-content: center;
    align-items: center;
    max-width: 640px;
    margin: 0 auto;
}}
.hero-icon {{
    width: 52px; height: 52px; border-radius: 14px; background: {RED};
    margin: 0 auto 14px;
    /* Instagram-style camera glyph (inline SVG is stripped by st.html's sanitizer) */
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2'%3E%3Crect x='3' y='3' width='18' height='18' rx='5'/%3E%3Ccircle cx='12' cy='12' r='4'/%3E%3Ccircle cx='17.5' cy='6.5' r='1' fill='white'/%3E%3C/svg%3E");
    background-size: 28px; background-repeat: no-repeat; background-position: center;
}}
.hero-title {{ font-size: 2.1rem; font-weight: 700; text-align: center; line-height: 1.2; margin: 0; color: #F1EFE8; }}
.hero-title span {{ color: {RED}; }}
.hero-sub {{ text-align: center; color: #B4B2A9; margin: 6px 0 18px; }}
.scroll-hint {{ text-align: center; color: #888780; font-size: 0.85rem; margin-top: 2.5rem; }}

/* 2. Saved posts */
.section-title {{ font-size: 1.3rem; font-weight: 600; color: #F1EFE8; margin: 0 0 0.5rem; }}
.section-title span {{ color: {RED}; font-weight: 400; font-size: 1rem; }}
.st-key-grid [data-testid="stVerticalBlockBorderWrapper"],
.st-key-grid div[class*="st-key-card_"] {{
    background: {PANEL}; border: 1px solid #2C2C2A; border-radius: 12px;
}}

/* 3. Popup: black body, red frame */
[data-testid="stDialog"] {{ background: rgba(0, 0, 0, 0.6); }}
[data-testid="stDialog"] > div {{ background: #0B0B0B; border: 1px solid {RED}; border-radius: 16px; }}
.status-strip {{
    background: {RED_DARK}; color: #fff; border-radius: 8px;
    padding: 8px 14px; font-weight: 600; margin-bottom: 4px;
}}
.comment {{
    background: {PANEL}; border-left: 2px solid {RED}; padding: 6px 10px; margin: 0 0 6px;
    color: #F1EFE8;
}}
.comment small {{ color: #888780; }}
.comments-title {{ color: #F09595; font-weight: 600; margin: 4px 0 6px; }}

/* Buttons: red primary, red-outlined secondary */
.stButton button[kind="secondary"], .stFormSubmitButton button[kind="secondaryFormSubmit"] {{
    border-color: {RED}; color: #F7C1C1; background: transparent;
}}
.stButton button[kind="secondary"]:hover, .stFormSubmitButton button[kind="secondaryFormSubmit"]:hover {{
    border-color: {RED}; color: #fff; background: {RED_DARK};
}}
a {{ color: #F09595 !important; }}
</style>
"""


def apply_theme() -> None:
    st.html(_CSS)
