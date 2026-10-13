"""Общие элементы оформления без логики исследований."""

from __future__ import annotations

import html

import streamlit as st

COLORS = ["#295BDE", "#36A28F", "#9980D8", "#D28B46", "#BB6092"]


def markup(text):
    st.markdown(text, unsafe_allow_html=True)


def escape(text):
    return html.escape(str(text))


def section(title, note=""):
    markup(f'<div class="section-line"><h2>{escape(title)}</h2><span>{escape(note)}</span></div>')
