# services.py
# ビジネスロジック（投資分析・LLM連携）

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from constants import (
    LLM_MODEL_NAME,
    LLM_TEMPERATURE,
    INVESTMENT_CAUTION_TEXT,
)
from utils import (
    build_user_prompt,
    extract_decision_from_text,
    format_analysis_result,
)


class StockAdvisorService:
    """
    注目株・保有株の分析を行うサービスクラス
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            model_name=LLM_MODEL_NAME,
            temperature=LLM_TEMPERATURE,
        )

    def analyze_stock(
        self,
        stock_name: str,
        position: str,
        additional_info: str = ""
    ) -> dict:
        """
        銘柄分析を行い、買い時・売り時・様子見を判断する
        """

        system_prompt = self._build_system_prompt()
        user_prompt = build_user_prompt(
            stock_name=stock_name,
            position=position,
            additional_info=additional_info,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        response = self.llm(messages)
        response_text = response.content

        decision_key = extract_decision_from_text(response_text)

        return format_analysis_result(
            response_text=response_text,
            decision_key=decision_key,
        )

    def _build_system_prompt(self) -> str:
        """
        システムプロンプト（安全性・一貫性担保）
        """
        return f"""
あなたは株式投資の一般的な情報提供を行うアシスタントです。

以下の制約を必ず守ってください。
- 特定銘柄の購入・売却を断定的に指示しない
- 必ず判断の根拠を説明する
- 将来予測は不確実であることを明示する
- 投資判断は自己責任である旨を含める

{INVESTMENT_CAUTION_TEXT}
""".strip()
