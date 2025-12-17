# main.py

from initialize import initialize_app
from services import StockAdvisorService
from components import (
    render_page,
    render_sidebar,
)


def main():
    # 初期化（env / page設定 / session_state）
    initialize_app()

    # サイドバー描画
    render_sidebar()

    # サービス生成（LLMロジック）
    service = StockAdvisorService()

    # 選択中メニューを取得（未選択時は「株の考察」）
    render_page(service)

if __name__ == "__main__":
    main()
