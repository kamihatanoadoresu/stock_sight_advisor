# main.py

from initialize import initialize_app
from services import StockAdvisorService
from components import (
    render_header,
    render_input_form,
    render_history,
)


def main():
    # 初期化（env / page設定 / session_state）
    initialize_app()

    # サービス生成（LLMロジック）
    service = StockAdvisorService()

    # UI描画
    render_header()
    render_input_form(service)
    render_history()


if __name__ == "__main__":
    main()
