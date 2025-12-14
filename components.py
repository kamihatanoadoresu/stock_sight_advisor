# components.py
# View部品（UIコンポーネント）

import streamlit as st

from services import StockAdvisorService
from constants import POSITION_OPTIONS
from utils import normalize_text


def render_header() -> None:
    """
    アプリのヘッダー表示
    """
    st.title("📈 注目株アドバイザー")
    st.write(
        "注目している株や保有株について、"
        "買い時・売り時・様子見の観点とその根拠を確認できます。"
    )
    st.divider()


def render_input_form(service: StockAdvisorService) -> None:
    """
    銘柄入力フォームと分析実行
    """
    with st.form(key="stock_analysis_form"):
        stock_name = st.text_input("銘柄名（例：トヨタ自動車）")
        position = st.selectbox("あなたの立場", POSITION_OPTIONS)
        additional_info = st.text_area(
            "補足情報（任意）",
            placeholder="気になっている点、購入理由、ニュースなど"
        )

        submitted = st.form_submit_button("分析する")

    if submitted:
        stock_name = normalize_text(stock_name)

        if not stock_name:
            st.error("銘柄名を入力してください。")
            return

        with st.spinner("分析中..."):
            result = service.analyze_stock(
                stock_name=stock_name,
                position=position,
                additional_info=additional_info,
            )

        st.session_state["analysis_history"].append(
            {
                "stock_name": stock_name,
                **result,
            }
        )

        render_analysis_result(result)


def render_analysis_result(result: dict) -> None:
    """
    分析結果の表示
    """
    st.divider()
    st.subheader("🧠 分析結果")

    st.markdown(f"### 判断：**{result['decision_label']}**")
    st.write(result["analysis_text"])


def render_history() -> None:
    """
    過去の分析履歴表示（簡易ダッシュボード）
    """
    if not st.session_state["analysis_history"]:
        return

    st.divider()
    st.subheader("📊 過去の分析履歴")

    for idx, item in enumerate(
        reversed(st.session_state["analysis_history"]),
        start=1
    ):
        with st.expander(f"{idx}. {item['stock_name']}"):
            st.write(f"判断：{item['decision_label']}")
            st.write(item["analysis_text"])
