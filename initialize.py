# initialize.py
# 初期化処理（環境・LLM・状態）

import streamlit as st
from dotenv import load_dotenv

from constants import APP_TITLE, MENU_STOCK_REVIEW


def load_environment() -> None:
    """
    環境変数（.env）を読み込む
    """
    load_dotenv()


def setup_page_config() -> None:
    """
    Streamlit のページ基本設定
    """
    st.set_page_config(
        page_title=APP_TITLE,
        layout="centered"
    )


def initialize_session_state() -> None:
    """
    セッションステートの初期化
    """
    if "analysis_history" not in st.session_state:
        st.session_state["analysis_history"] = []

    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = []

    if "portfolio" not in st.session_state:
        st.session_state["portfolio"] = []
    
    if "selected_menu" not in st.session_state:
        st.session_state["selected_menu"] = MENU_STOCK_REVIEW


def initialize_app() -> None:
    """
    アプリ起動時に呼び出す初期化処理まとめ
    """
    load_environment()
    setup_page_config()
    initialize_session_state()
    # st.title(APP_TITLE)
