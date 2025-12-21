# constants.py
# 定数・ルール・制約集

import json
from pathlib import Path
from typing import Dict, List, Tuple

# =========================
# アプリ基本情報
# =========================

APP_TITLE = "StockSight Advisor"
APP_DESCRIPTION = """
注目株・保有株について、
「今は買い時／売り時か？」を根拠付きで整理し、
投資判断をサポートするアプリです。
"""

DISCLAIMER_TEXT = """
※ 本アプリは投資助言を目的としたものではありません。
最終的な投資判断はご自身の責任で行ってください。
"""

INVESTMENT_CAUTION_TEXT = """
※ 本アプリは一般的な情報提供を目的としています。
※ 特定の銘柄の売買を保証・推奨するものではありません。
※ 最終的な投資判断はご自身の責任で行ってください。
"""

# =========================
# LLM設定
# =========================

LLM_MODEL_NAME = "gpt-4o-mini"
LLM_TEMPERATURE = 0.2

# =========================
# 投資判断ラベル
# =========================

DECISION_BUY = "buy"
DECISION_SELL = "sell"
DECISION_HOLD = "hold"

DECISION_LABELS_JP = {
    DECISION_BUY: "買い時の可能性あり",
    DECISION_SELL: "売却を検討する局面",
    DECISION_HOLD: "様子見が妥当"
}

# =========================
# LLMシステムプロンプト
# =========================

SYSTEM_PROMPT = """
あなたは投資判断を補助するAIアシスタントです。
以下の制約を必ず守ってください。

【重要な制約】
・特定の銘柄の購入・売却を断定的に指示しない
・事実や一般的な傾向に基づいて説明する
・不確実な情報については、その旨を明示する
・過度に楽観的・悲観的な表現を避ける

【回答フォーマット】
以下の見出し構成を必ず守ってください。

【現在の状況】
【買い／売り／様子見の判断】
【判断の根拠】
【注意すべきリスク】
【今後考えられるシナリオ】

冷静で客観的なトーンで回答してください。
"""

# =========================
# UI表示用テキスト
# =========================

STOCK_NAME_LABEL = "分析したい銘柄名を入力してください"
POSITION_LABEL = "あなたの立場を選択してください"
POSITION_OPTIONS = ["注目株", "保有株"]
PERIOD_OPTIONS = ["3ヶ月", "半年", "1年", "3年"]

ADDITIONAL_INFO_LABEL = "補足情報（任意）"
ADDITIONAL_INFO_PLACEHOLDER = (
    "気になっているニュース、購入価格、懸念点などがあれば入力してください"
)

EXECUTE_BUTTON_LABEL = "分析を実行"
LOADING_MESSAGE = "投資判断を分析中です。しばらくお待ちください..."
RESULT_SECTION_TITLE = "投資判断結果"
ERROR_MESSAGE = "分析中にエラーが発生しました。もう一度お試しください。"

# ===== サイドバーメニュー =====
MENU_STOCK_REVIEW = "株の考察"
MENU_CANDIDATE_STOCKS = "有力株の表示"
MENU_CHART = "チャートの表示"
MENU_TREND = "傾向分析"

MENU_OPTIONS = [
    MENU_CANDIDATE_STOCKS,
    MENU_CHART,
    MENU_TREND,
    MENU_STOCK_REVIEW,
]

# ===== キャッシュ設定 =====
CACHE_FILE_PATH = "ipo_cache.pkl"
CACHE_EXPIRY_DAYS = 7  # キャッシュの有効期限（日数）

# ===== チャート表示設定 =====
STOCKS_JSON_PATH = "stocks.json"

def load_stocks_data() -> Dict:
    """
    stocks.jsonから銘柄データを読み込む
    """
    json_path = Path(__file__).parent / STOCKS_JSON_PATH
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # ファイルがない場合は空の辞書を返す
        return {}

def get_tickers_and_names(position: str = "保有株") -> Tuple[List[str], Dict[str, str]]:
    """
    選択された区分（保有株/注目株）に応じたティッカーリストと名前辞書を取得
    
    Args:
        position: "保有株" または "注目株"
    
    Returns:
        (tickers_list, names_dict)
    """
    stocks_data = load_stocks_data()
    
    if position in stocks_data:
        return stocks_data[position]['tickers'], stocks_data[position]['names']
    else:
        # デフォルトは保有株
        if "保有株" in stocks_data:
            return stocks_data["保有株"]['tickers'], stocks_data["保有株"]['names']
        return [], {}

# 後方互換性のためにデフォルト値を設定（保有株）
TICKERS, TITLE_DICT = get_tickers_and_names("保有株")
