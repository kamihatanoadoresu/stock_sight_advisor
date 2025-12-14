# utils.py
# 汎用ロジック・補助関数集

from typing import Dict

from constants import (
    DECISION_BUY,
    DECISION_SELL,
    DECISION_HOLD,
    DECISION_LABELS_JP,
)


def normalize_text(text: str) -> str:
    """
    ユーザー入力テキストの前後空白を除去し、
    None対策も含めて安全に正規化する
    """
    if not text:
        return ""
    return text.strip()


def build_user_prompt(
    stock_name: str,
    position: str,
    additional_info: str
) -> str:
    """
    ユーザー入力をもとに LLM に渡すプロンプトを生成する
    """
    stock_name = normalize_text(stock_name)
    additional_info = normalize_text(additional_info)

    prompt = f"""
銘柄名：{stock_name}
ユーザーの立場：{position}
"""

    if additional_info:
        prompt += f"""
補足情報：
{additional_info}
"""

    return prompt.strip()


def decision_key_to_label(decision_key: str) -> str:
    """
    buy / sell / hold の内部キーを
    画面表示用の日本語ラベルに変換する
    """
    return DECISION_LABELS_JP.get(decision_key, "判断不能")


def extract_decision_from_text(response_text: str) -> str:
    """
    LLMの回答テキストから
    買い / 売り / 様子見 を簡易的に判定する

    ※ 将来RAGや構造化出力に置き換えやすい設計
    """
    if not response_text:
        return DECISION_HOLD

    text = response_text.lower()

    if "買い" in text:
        return DECISION_BUY
    if "売り" in text:
        return DECISION_SELL

    return DECISION_HOLD


def format_analysis_result(
    response_text: str,
    decision_key: str
) -> Dict[str, str]:
    """
    分析結果をダッシュボード表示しやすい形に整形
    """
    return {
        "decision_key": decision_key,
        "decision_label": decision_key_to_label(decision_key),
        "analysis_text": response_text,
    }
