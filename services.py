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

        response = self.llm.invoke(messages)
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



# ↓ここから---------------------------------
# データ取得・分析ロジック（Service層）

import re
import json
import pickle
import os
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup
import streamlit as st

from constants import CACHE_FILE_PATH, CACHE_EXPIRY_DAYS

# 失敗したティッカーのキャッシュファイル
FAILED_TICKERS_PATH = "failed_tickers.json"


class IPOStockService:
    """
    有力IPO銘柄を抽出するサービス
    """

    # =========================
    # 1. JPX IPO一覧取得
    # =========================
    def get_jpx_ipo_list_multi_year(self, years: int = 5) -> pd.DataFrame:
        base_url = "https://www.jpx.co.jp/listing/stocks/new/"
        suffix_list = [
            "index.html",
            "00-archives-01.html",
            "00-archives-02.html",
            "00-archives-03.html",
            "00-archives-04.html",
        ]

        records = []

        for i in range(min(years, len(suffix_list))):
            url = base_url + suffix_list[i]

            try:
                r = requests.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10,
                )
                r.encoding = r.apparent_encoding
                soup = BeautifulSoup(r.text, "html.parser")

                table = soup.find("table")
                if table is None:
                    continue

                rows = table.find_all("tr")[2:]

                idx = 0
                while idx < len(rows) - 1:
                    tr1 = rows[idx]
                    tr2 = rows[idx + 1]

                    tds1 = tr1.find_all("td")
                    tds2 = tr2.find_all("td")

                    try:
                        listed_date = tds1[0].get_text(strip=True).split("（")[0]
                        company = tds1[1].find("a").get_text(strip=True)
                        code = tds1[2].get_text(strip=True)
                        market = tds2[0].get_text(strip=True)

                        price_text = tds2[3].get_text(strip=True) if len(tds2) > 3 else ""
                        if "～" in price_text:
                            price_text = price_text.split("～")[-1]

                        public_price = (
                            int(price_text.replace(",", ""))
                            if price_text.replace(",", "").isdigit()
                            else None
                        )

                        records.append(
                            {
                                "上場日": listed_date,
                                "市場": market,
                                "証券コード": code,
                                "企業名": company,
                                "公募価格": public_price,
                            }
                        )
                    except Exception:
                        pass

                    idx += 2

            except Exception:
                continue
        return pd.DataFrame(records)

    # =========================
    # 2. 現在株価取得（yfinance）
    # =========================
    def get_current_prices(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["現在株価"] = None
        # 可能であれば yfinance.download を使って小分けで一括取得し、失敗トークンをスキップする
        codes = [str(df.at[i, "証券コード"]).zfill(4) + ".T" for i in df.index]

        # --- failed tickers キャッシュをロードし、TTL 内のものはスキップ ---
        def _load_failed_tickers():
            try:
                if not os.path.exists(FAILED_TICKERS_PATH):
                    return {}
                with open(FAILED_TICKERS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # TTL チェック（CACHE_EXPIRY_DAYS を利用）
                valid = {}
                now = datetime.now()
                for tk, ts in data.items():
                    try:
                        t = datetime.fromisoformat(ts)
                        if now - t < timedelta(days=CACHE_EXPIRY_DAYS):
                            valid[tk] = ts
                    except Exception:
                        continue
                # 保存を更新（古いエントリ削除）
                with open(FAILED_TICKERS_PATH, 'w', encoding='utf-8') as f:
                    json.dump(valid, f, ensure_ascii=False, indent=2)
                return valid
            except Exception:
                return {}

        def _add_failed_ticker(ticker: str):
            try:
                data = {}
                if os.path.exists(FAILED_TICKERS_PATH):
                    with open(FAILED_TICKERS_PATH, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                data[ticker] = datetime.now().isoformat()
                with open(FAILED_TICKERS_PATH, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        def _remove_failed_ticker(ticker: str):
            try:
                if not os.path.exists(FAILED_TICKERS_PATH):
                    return
                with open(FAILED_TICKERS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if ticker in data:
                    del data[ticker]
                    with open(FAILED_TICKERS_PATH, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        failed_cache = _load_failed_tickers()
        skip_codes = set([c for c in codes if c in failed_cache])

        # 実際に試行するコード群
        trial_codes = [c for c in codes if c not in skip_codes]

        def _assign_from_bulk(bulk, codes_subset):
            if bulk is None or bulk.empty:
                return []
            failed = []
            # bulk may be multiindexed (ticker, field) or single
            for code in codes_subset:
                try:
                    if isinstance(bulk.columns, pd.MultiIndex):
                        if (code, 'Close') in bulk.columns:
                            val = bulk[(code, 'Close')].dropna()
                            if not val.empty:
                                idx = df.index[codes.index(code)]
                                df.at[idx, "現在株価"] = round(val.iloc[-1])
                            else:
                                failed.append(code)
                        else:
                            failed.append(code)
                    else:
                        # single ticker case: try to read 'Close'
                        if 'Close' in bulk.columns:
                            val = bulk['Close'].dropna()
                            if not val.empty:
                                idx = df.index[codes.index(code)]
                                df.at[idx, "現在株価"] = round(val.iloc[-1])
                            else:
                                failed.append(code)
                        else:
                            failed.append(code)
                except Exception:
                    failed.append(code)
            return failed

        # 小分けバッチ（例えば 10 件ずつ）で取得を試みる
        batch_size = 10
        remaining = []
        for i in range(0, len(trial_codes), batch_size):
            subset = trial_codes[i : i + batch_size]
            try:
                bulk = yf.download(tickers=subset, period="1d", interval="1d", group_by='ticker', threads=False, progress=False)
                failed = _assign_from_bulk(bulk, subset)
                remaining.extend(failed)
            except Exception:
                # バルク失敗時は個別取得へフォールバック（ただし短時間で切り上げる）
                remaining.extend(subset)

        # 個別フォールバック（残った銘柄のみ）
        for code in remaining:
            try:
                ticker = yf.Ticker(code)
                data = ticker.history(period="1d")
                if not data.empty:
                    idx = df.index[codes.index(code)]
                    df.at[idx, "現在株価"] = round(data["Close"].iloc[-1])
                    # 成功したら failed キャッシュから削除
                    _remove_failed_ticker(code)
                else:
                    # 失敗ならキャッシュに追加
                    _add_failed_ticker(code)
            except Exception:
                # 失敗としてキャッシュに追加して継続
                _add_failed_ticker(code)
                continue

        # 既にスキップしていたコードはログに残すが処理継続
        for code in skip_codes:
            # skipされたコードはキャッシュに入っているため何もしない
            continue

        return df

    # =========================
    # 3. 時価総額取得（IR BANK）
    # =========================
    def get_market_cap(self, code: str) -> float | None:
        try:
            url = f"https://irbank.net/{code}/cap"
            r = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            soup = BeautifulSoup(r.content, "html.parser")

            tds = soup.select("table#tbc tbody tr td")
            for td in tds:
                text = td.get_text(strip=True)
                match = re.match(r"(\d+)(億)(\d+)?(万)?", text)
                if match:
                    oku = int(match.group(1))
                    man = int(match.group(3)) if match.group(3) else 0
                    return oku + man / 10000

            return None

        except Exception:
            return None

    # =========================
    # 4. オーナー創業社長判定
    # =========================
    def is_owner_ceo(self, code: str) -> bool:
        try:
            url = f"https://irbank.net/{code}/officer"
            r = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            soup = BeautifulSoup(r.content, "html.parser")

            for tr in soup.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    role_text = tds[1].get_text(strip=True)
                    match = re.search(r"\(([\d.]+)%\)", role_text)
                    ratio = float(match.group(1)) if match else 0.0

                    if "取締役" in role_text and ratio >= 40:
                        return True

            return False

        except Exception:
            return False

    # =========================
    # 5. 有力IPO抽出（入口）
    # =========================
    def get_promising_ipos(self) -> pd.DataFrame:
        """
        有力IPO銘柄を抽出する
        キャッシュがあればそれを返し、なければ新規取得する
        """
        # JPX IPO一覧取得
        df = self.get_jpx_ipo_list_multi_year(years=5)

        if df.empty or "証券コード" not in df.columns:
            return pd.DataFrame(
                columns=[
                    "証券コード",
                    "企業名",
                    "上場日",
                    "現在株価",
                    "公募価格",
                    "時価総額",
                ]
            )

        # 現在株価取得
        with st.spinner(f"📊 {len(df)}件のIPO銘柄から株価を取得中..."):
            df = self.get_current_prices(df)

        # 時価総額取得
        with st.spinner("💰 時価総額を取得中..."):
            df["時価総額"] = df["証券コード"].apply(self.get_market_cap)

        # オーナー創業社長判定
        with st.spinner("👔 オーナー創業社長を判定中..."):
            df["オーナー創業社長"] = df["証券コード"].apply(self.is_owner_ceo)

        # 上場年を抽出
        df["上場年"] = df["上場日"].str[:4].astype(int)

        # フィルタ適用
        df_filtered = df.copy()

        # 上場年フィルタ（現在から10年以内）
        year_limit = datetime.now().year - 10
        df_filtered = df_filtered[df_filtered["上場年"] >= year_limit]

        # 公募価格あり
        df_filtered = df_filtered[df_filtered["公募価格"].notnull()]

        # 現在株価あり
        df_filtered = df_filtered[df_filtered["現在株価"].notnull()]

        # 現在株価 < 公募価格
        df_filtered = df_filtered[df_filtered["現在株価"] < df_filtered["公募価格"]]

        # 時価総額が数値であることを確認
        df_filtered["時価総額"] = pd.to_numeric(df_filtered["時価総額"], errors="coerce")
        df_filtered = df_filtered[df_filtered["時価総額"].notnull()]

        # 時価総額が 30 以上 700 以下
        df_filtered = df_filtered[
            (df_filtered["時価総額"] >= 30) & (df_filtered["時価総額"] <= 700)
        ]

        # オーナー創業社長が True
        df_filtered = df_filtered[df_filtered["オーナー創業社長"] == True]

        # 必要な列のみ返す
        result = df_filtered[
            ["証券コード", "企業名", "上場日", "現在株価", "公募価格", "時価総額"]
        ].reset_index(drop=True)

        # キャッシュに保存
        self.save_cache(result)

        return result

    # =========================
    # 6. キャッシュ管理
    # =========================
    def save_cache(self, df: pd.DataFrame) -> None:
        """データをキャッシュファイルに保存"""
        try:
            cache_data = {
                "data": df,
                "timestamp": datetime.now(),
            }
            with open(CACHE_FILE_PATH, "wb") as f:
                pickle.dump(cache_data, f)
        except Exception as e:
            st.warning(f"キャッシュの保存に失敗しました: {e}")

    # ---------------------------
    # failed tickers キャッシュ管理用の公開API
    # ---------------------------
    def get_failed_tickers(self) -> list:
        """現在キャッシュにある failed tickers の一覧を返す"""
        try:
            if not os.path.exists(FAILED_TICKERS_PATH):
                return []
            with open(FAILED_TICKERS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return list(data.keys())
        except Exception:
            return []

    def clear_failed_tickers(self) -> None:
        """failed tickers キャッシュを削除する"""
        try:
            if os.path.exists(FAILED_TICKERS_PATH):
                os.remove(FAILED_TICKERS_PATH)
        except Exception:
            pass

    def load_cache(self) -> tuple[pd.DataFrame | None, datetime | None]:
        """
        キャッシュファイルを読み込む
        Returns: (DataFrame, タイムスタンプ) または (None, None)
        """
        if not os.path.exists(CACHE_FILE_PATH):
            return None, None

        try:
            with open(CACHE_FILE_PATH, "rb") as f:
                cache_data = pickle.load(f)
            return cache_data.get("data"), cache_data.get("timestamp")
        except Exception as e:
            st.warning(f"キャッシュの読み込みに失敗しました: {e}")
            return None, None

    def is_cache_valid(self, timestamp: datetime | None) -> bool:
        """キャッシュが有効期限内かどうかをチェック"""
        if timestamp is None:
            return False

        expiry_date = timestamp + timedelta(days=CACHE_EXPIRY_DAYS)
        return datetime.now() < expiry_date