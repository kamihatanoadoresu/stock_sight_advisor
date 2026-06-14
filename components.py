# components.py
# View部品（UIコンポーネント）

import streamlit as st
from typing import TYPE_CHECKING
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import warnings
import ta
warnings.simplefilter('ignore')

from constants import (
    MENU_OPTIONS,
    MENU_CHART,
    MENU_TREND,
    MENU_STOCK_REVIEW,
    MENU_CANDIDATE_STOCKS,
    POSITION_OPTIONS,
    PERIOD_OPTIONS,
    TICKERS,
    TITLE_DICT,
    get_tickers_and_names,
)
from utils import normalize_text
from services import StockAdvisorService
from services import IPOStockService


def render_sidebar() -> None:
    """サイドバー描画"""

    with st.sidebar:
        st.title("📌 メニュー")

        # メインメニュー（プルダウン）
        selected_menu = st.selectbox(
            "表示内容を選択",
            MENU_OPTIONS,
            key="selected_menu"
        )

        st.divider()

        is_position_enabled = selected_menu in [MENU_CHART, MENU_TREND, MENU_STOCK_REVIEW]
        is_chart_mode = selected_menu in [MENU_CHART, MENU_TREND]

        st.radio(
            "株の区分",
            POSITION_OPTIONS,
            key="sidebar_position",
            disabled=not is_position_enabled
        )

        st.selectbox(
            "期間",
            PERIOD_OPTIONS,
            key="sidebar_period",
            disabled=not is_chart_mode
        )

def render_page(service: "StockAdvisorService") -> None:
    """
    サイドバーの選択状態に応じて
    適切なページを描画する
    """

    selected_menu = st.session_state["selected_menu"]

    if selected_menu == MENU_STOCK_REVIEW:
        render_header()
        render_stock_judge()
    elif selected_menu == MENU_CANDIDATE_STOCKS:
        render_promising_stocks()
    elif selected_menu == MENU_CHART:
        render_chart_page()
    elif selected_menu == MENU_TREND:
        render_trend_analysis_page()
    else:
        st.title(selected_menu)
        st.info("この機能は現在準備中です。")


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


def render_input_form(service: "StockAdvisorService") -> None:
    """
    銘柄入力フォームと分析実行
    """
    with st.form(key="stock_analysis_form"):
        stock_name = st.text_input("銘柄名（例：トヨタ自動車）")
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
            position = st.session_state.get("sidebar_position", "注目株")

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


@st.cache_data(ttl=3600)
def fetch_fundamentals(ticker: str) -> dict:
    """
    基本的な財務指標をyfinanceから取得して正規化して返す（best-effort）
    戻り値: dict of metrics (可能な限り値を埋める)
    """
    metrics = {}
    try:
        tk = yf.Ticker(ticker)

        info = tk.info or {}

        # 市場データ
        metrics['marketCap'] = info.get('marketCap')
        metrics['trailingPE'] = info.get('trailingPE')

        # 財務諸表（年度・四半期ベースのDataFrameが返ることがある）
        try:
            bs = tk.balance_sheet
        except Exception:
            bs = None

        try:
            fin = tk.financials
        except Exception:
            fin = None

        try:
            earnings = tk.earnings
        except Exception:
            earnings = None

        # 最新列を取得するヘルパー
        def latest_from_df(df):
            if df is None or df.empty:
                return None
            try:
                return df.iloc[:, 0]
            except Exception:
                return None

        bs_latest = latest_from_df(bs)
        fin_latest = latest_from_df(fin)

        # 総資産・自己資本（ラベルが多様なため、キーワードで緩やかに探索する）
        def _find_in_series(s, patterns):
            if s is None:
                return None
            try:
                for idx in s.index:
                    lab = str(idx).lower()
                    for p in patterns:
                        if p in lab:
                            val = s.get(idx)
                            if val is not None and (not (isinstance(val, float) and pd.isna(val))):
                                return val
                return None
            except Exception:
                return None

        metrics['totalAssets'] = None
        metrics['totalEquity'] = None
        if bs_latest is not None:
            metrics['totalAssets'] = _find_in_series(bs_latest, ['total asset', 'totalassets', 'totalasset', 'assets'])
            metrics['totalEquity'] = _find_in_series(bs_latest, ['total stockholder', 'totalstockholder', 'totalstock', 'total shareholder', 'totalshareholder', 'total equity', 'totalequity', 'shareholders'])

        # 有利子負債（候補）: info の totalDebt を優先、なければバランスシートから long/short debt を合算して探す
        total_debt = None
        if info.get('totalDebt') is not None:
            total_debt = info.get('totalDebt')
        else:
            # try several debt-related labels in bs_latest
            if bs_latest is not None:
                td1 = _find_in_series(bs_latest, ['long term debt', 'longtermdebt', 'long term liabilities', 'long term borrowings'])
                td2 = _find_in_series(bs_latest, ['short term debt', 'shorttermdebt', 'short term borrowings', 'short term liabilities'])
                # 合算できるものは合算、なければ見つかったものを使う
                try:
                    vals = [v for v in [td1, td2] if v is not None]
                    if vals:
                        total_debt = sum(vals)
                    else:
                        # fallback: any label containing 'debt' or 'liab' might be usable
                        total_debt = _find_in_series(bs_latest, ['debt', 'liab'])
                except Exception:
                    total_debt = None
        metrics['totalDebt'] = total_debt

        # 損益系（ラベルが多様なためパターンで探索）
        metrics['revenue'] = None
        metrics['operatingIncome'] = None
        metrics['netIncome'] = None
        if fin is not None and not fin.empty:
            try:
                # fin は DataFrame。行ラベルをキーワードで探索して最新列の値を取得する
                def _find_label_in_df(df, patterns):
                    for idx in df.index:
                        lab = str(idx).lower()
                        for p in patterns:
                            if p in lab:
                                return idx
                    return None

                rev_label = _find_label_in_df(fin, ['total revenue', 'totalrevenue', 'revenue', 'sales'])
                op_label = _find_label_in_df(fin, ['operating income', 'operatingincome', 'operating', 'total operating income', 'ebit'])
                net_label = _find_label_in_df(fin, ['net income', 'netincome', 'net profit'])

                def _first_nonnull_from_row(row):
                    for v in row.values:
                        try:
                            if v is None:
                                continue
                            if isinstance(v, float) and pd.isna(v):
                                continue
                            return v
                        except Exception:
                            continue
                    return None

                if rev_label is not None:
                    metrics['revenue'] = _first_nonnull_from_row(fin.loc[rev_label])
                if op_label is not None:
                    metrics['operatingIncome'] = _first_nonnull_from_row(fin.loc[op_label])
                if net_label is not None:
                    metrics['netIncome'] = _first_nonnull_from_row(fin.loc[net_label])
            except Exception:
                metrics['revenue'] = None
                metrics['operatingIncome'] = None
                metrics['netIncome'] = None

        # EPS: 優先的にinfoの値
        metrics['eps'] = info.get('trailingEps') or info.get('eps') or None
        # 配当性向（payoutRatio）
        metrics['payoutRatio'] = info.get('payoutRatio')

        # EPS履歴（earnings DataFrameがあれば抽出） - best-effort
        metrics['eps_history'] = None
        try:
            if earnings is not None and not earnings.empty:
                # yfinance の earnings は列に 'Earnings' を持つことが多い
                if 'Earnings' in earnings.columns:
                    metrics['eps_history'] = earnings['Earnings'].astype(float).tolist()
                else:
                    # 他の列がある場合は最初の列を使う
                    metrics['eps_history'] = earnings.iloc[:, 0].astype(float).tolist()
        except Exception:
            metrics['eps_history'] = None

        # 優待改悪／廃止情報は外部ソースが必要なため未実装（N/A）
        metrics['benefit_change_announced'] = None

        # 収益性などの比率
        try:
            if metrics.get('totalAssets') is not None and metrics.get('totalEquity') is not None and metrics.get('totalAssets') != 0:
                metrics['equityRatio'] = metrics['totalEquity'] / metrics['totalAssets']
            else:
                # yfinance may provide bookValue, totalAssets or returnOnEquity; try common fallbacks
                try:
                    ta_val = info.get('totalAssets')
                    te_val = info.get('totalStockholderEquity') or info.get('totalShareHolderEquity') or info.get('totalEquity')
                    if ta_val and te_val:
                        metrics['equityRatio'] = te_val / ta_val
                    else:
                        metrics['equityRatio'] = None
                except Exception:
                    metrics['equityRatio'] = None
        except Exception:
            metrics['equityRatio'] = None

        # ROE
        try:
            if metrics.get('netIncome') and metrics.get('totalEquity'):
                metrics['ROE'] = metrics['netIncome'] / metrics['totalEquity']
            else:
                metrics['ROE'] = info.get('returnOnEquity')
        except Exception:
            metrics['ROE'] = None

        # 営業利益率
        try:
            if metrics.get('operatingIncome') and metrics.get('revenue'):
                metrics['operatingMargin'] = metrics['operatingIncome'] / metrics['revenue']
            else:
                metrics['operatingMargin'] = None
        except Exception:
            metrics['operatingMargin'] = None

        # 成長率: ラベルをパターンで探して最新と前期で成長率を算出する（best-effort）
        def _find_label_in_df(df, patterns):
            if df is None:
                return None
            try:
                for idx in df.index:
                    lab = str(idx).lower()
                    for p in patterns:
                        if p in lab:
                            return idx
                return None
            except Exception:
                return None

        def calc_growth_by_patterns(df, patterns):
            if df is None or df.empty:
                return None
            lbl = _find_label_in_df(df, patterns)
            if lbl is None:
                return None
            try:
                row = df.loc[lbl]
                # pick first two non-null values (latest first)
                nonnull = []
                for v in row.values:
                    try:
                        if v is None:
                            continue
                        if isinstance(v, float) and pd.isna(v):
                            continue
                        nonnull.append(v)
                        if len(nonnull) >= 2:
                            break
                    except Exception:
                        continue
                if len(nonnull) < 2:
                    return None
                latest, prev = nonnull[0], nonnull[1]
                if prev is None or prev == 0:
                    return None
                return (latest - prev) / abs(prev)
            except Exception:
                return None

        metrics['revenueGrowth'] = None
        metrics['operatingIncomeGrowth'] = None
        if fin is not None and not fin.empty:
            metrics['revenueGrowth'] = calc_growth_by_patterns(fin, ['total revenue', 'totalrevenue', 'revenue', 'sales'])
            metrics['operatingIncomeGrowth'] = calc_growth_by_patterns(fin, ['operating income', 'operatingincome', 'operating', 'ebit'])

        # PER
        metrics['PER'] = info.get('trailingPE') or info.get('forwardPE')

    except Exception:
        return {}

    return metrics


def evaluate_buy_rules(metrics: dict) -> dict:
    """
    指定されたルールで判定を行い、各ルールごとの通過可否を返す
    """
    res = {}
    # 優待目的
    # compute debt/equity safely
    _td = metrics.get('totalDebt')
    _te = metrics.get('totalEquity')
    try:
        debt_equity_ok = (_td is not None and _te is not None and _te != 0 and (_td / _te) <= 1.0)
    except Exception:
        debt_equity_ok = False

    res['yutai'] = {
        '自己資本比率>=30%': metrics.get('equityRatio') is not None and metrics.get('equityRatio') >= 0.30,
        '有利子負債自己資本比率<=100%': debt_equity_ok,
        '経常利益(営業利益)が黒字': metrics.get('operatingIncome') is not None and metrics.get('operatingIncome') > 0,
        'EPSが黒字': metrics.get('eps') is not None and metrics.get('eps') > 0,
    }

    # 最高益だが株価下落中（成長性重視）
    res['growth_top'] = {
        '経常利益成長率>=20%': metrics.get('operatingIncomeGrowth') is not None and metrics.get('operatingIncomeGrowth') >= 0.20,
        '売上高成長率>=15%': metrics.get('revenueGrowth') is not None and metrics.get('revenueGrowth') >= 0.15,
        '営業利益率>=10%': metrics.get('operatingMargin') is not None and metrics.get('operatingMargin') >= 0.10,
        '自己資本比率>=40%': metrics.get('equityRatio') is not None and metrics.get('equityRatio') >= 0.40,
        'ROE>=15%': metrics.get('ROE') is not None and metrics.get('ROE') >= 0.15,
        'PER between 15 and 25': metrics.get('PER') is not None and (15 <= metrics.get('PER') <= 25),
    }

    # 上場5年以内・成長性志向
    res['early_growth'] = {
        '時価総額<=500億円': metrics.get('marketCap') is not None and metrics.get('marketCap') <= 500 * 10**8,  # 500億円
        '売上高成長率>=20%': metrics.get('revenueGrowth') is not None and metrics.get('revenueGrowth') >= 0.20,
        '経常利益成長率>=20%': metrics.get('operatingIncomeGrowth') is not None and metrics.get('operatingIncomeGrowth') >= 0.20,
        '自己資本比率>=30%': metrics.get('equityRatio') is not None and metrics.get('equityRatio') >= 0.30,
        '営業利益率>=10%': metrics.get('operatingMargin') is not None and metrics.get('operatingMargin') >= 0.10,
        'PER between 15 and 30': metrics.get('PER') is not None and (15 <= metrics.get('PER') <= 30),
    }

    return res


def evaluate_sell_rules(metrics: dict) -> dict:
    """
    売りロジックの判定を行う（優待株の指標 / キャピタルゲインの指標）
    """
    res = {}

    # ① 優待株の指標（売りシグナル）
    res['優待株の指標'] = {
        '自己資本比率<=30%': metrics.get('equityRatio') is not None and metrics.get('equityRatio') <= 0.30,
        'EPSが2期連続マイナス': False if metrics.get('eps_history') is None else (len(metrics.get('eps_history')) >= 2 and metrics.get('eps_history')[-1] < 0 and metrics.get('eps_history')[-2] < 0),
        '優待改悪/廃止発表あり': True if metrics.get('benefit_change_announced') else False,
        '配当性向>=80%': metrics.get('payoutRatio') is not None and metrics.get('payoutRatio') >= 0.80,
    }

    # ② キャピタルゲインの指標（売りシグナル）
    res['キャピタルゲインの指標'] = {
        '売上高成長率<=15%': metrics.get('revenueGrowth') is not None and metrics.get('revenueGrowth') <= 0.15,
        '経常利益成長率<=20%': metrics.get('operatingIncomeGrowth') is not None and metrics.get('operatingIncomeGrowth') <= 0.20,
        'PER>=30': metrics.get('PER') is not None and metrics.get('PER') >= 30,
        '営業利益率<=5%': metrics.get('operatingMargin') is not None and metrics.get('operatingMargin') <= 0.05,
    }

    return res


def render_stock_judge() -> None:
    """
    銘柄ドロップダウンで選択した銘柄について、条件達成表と最終ジャッジを表示
    """
    st.subheader("🔎 銘柄の条件チェック（簡易判定）")

    # 表示名マップ（内部キー -> 表示ラベル）
    section_title_map = {
        'yutai': '優待目的の判定',
        'growth_top': '配当金目的の判定',
        'early_growth': 'キャピタルゲイン目的の判定'
    }

    # 表示用フォーマッタ（欠損値と nan を適切に N/A 表示にする）
    def _is_missing(v):
        try:
            return v is None or (isinstance(v, float) and pd.isna(v))
        except Exception:
            return v is None

    def fmt_num(v, precision=2):
        if _is_missing(v):
            return 'N/A'
        try:
            return f"{v:.{precision}f}"
        except Exception:
            return str(v)

    def fmt_percent(v, precision=1):
        if _is_missing(v):
            return 'N/A'
        try:
            return f"{v*100:.{precision}f}%"
        except Exception:
            return str(v)

    def fmt_money(v):
        if _is_missing(v):
            return 'N/A'
        try:
            return f"{int(v):,}"
        except Exception:
            return str(v)

    # サイドバーの区分選択を使用する（重複 UI を避ける）
    position = st.session_state.get('sidebar_position', '保有株')

    # 売買の目的ラジオ（買いロジックは表示、売りは未実装表示）
    intent = st.radio("目的を選択", options=["買いたい", "売りたい"], horizontal=True, key='judge_intent')

    tickers, title_dict = get_tickers_and_names(position)

    if not tickers:
        st.info('銘柄リストが空です。stocks.jsonを確認してください。')
        return

    # ドロップダウンで銘柄選択
    options = [f"{title_dict.get(t, t)} ({t})" for t in tickers]
    choice = st.selectbox('銘柄を選択してください', options, key='judge_ticker')
    selected_ticker = choice.split('(')[-1].strip(')')

    if intent == '売りたい':
        # 売りロジックを実行して表示
        with st.spinner('財務データ取得中...'):
            metrics = fetch_fundamentals(selected_ticker)

        if not metrics:
            st.error('財務データが取得できませんでした。')
            return

        sell_evals = evaluate_sell_rules(metrics)

        for section, checks in sell_evals.items():
            st.markdown(f"**{section} の判定**")
            rows = []
            for k, v in checks.items():
                val = v
                metric_display = ''
                try:
                    if '自己資本比率' in k:
                        metric_display = fmt_percent(metrics.get('equityRatio'), precision=2)
                    if 'EPS' in k:
                        # EPS履歴の末尾2期を表示
                        eps_hist = metrics.get('eps_history')
                        if eps_hist and len(eps_hist) >= 2:
                            metric_display = f"{fmt_num(eps_hist[-2],2)}, {fmt_num(eps_hist[-1],2)}"
                        elif metrics.get('eps') is not None:
                            metric_display = fmt_num(metrics.get('eps'), 2)
                        else:
                            metric_display = 'N/A'
                    if '優待改悪' in k or '廃止' in k:
                        metric_display = 'あり' if metrics.get('benefit_change_announced') else 'N/A'
                    if '配当性向' in k:
                        metric_display = fmt_percent(metrics.get('payoutRatio'), precision=1)
                    if '売上高成長率' in k:
                        metric_display = fmt_percent(metrics.get('revenueGrowth'), precision=1)
                    if '経常利益成長率' in k:
                        metric_display = fmt_percent(metrics.get('operatingIncomeGrowth'), precision=1)
                    if 'PER' in k:
                        metric_display = fmt_num(metrics.get('PER'), precision=2)
                    if '営業利益率' in k:
                        metric_display = fmt_percent(metrics.get('operatingMargin'), precision=1)
                except Exception:
                    metric_display = 'N/A'

                rows.append({
                    '判定項目': k,
                    '該当': '✅' if val else '❌',
                    '値': metric_display
                })

            df_checks = pd.DataFrame(rows)
            st.dataframe(df_checks, use_container_width=True)

        # 最終ジャッジ（単純まとめ）
        final_sell = any(all(v for v in checks.values()) for checks in sell_evals.values())
        if final_sell:
            st.warning('総合判定: 売却を検討する条件が揃っています（注意検討）')
        else:
            st.info('総合判定: 現時点で売却条件は揃っていません。')
        return

    # 以下は「買いたい」を選択した場合の表示（買いロジック）
    with st.spinner('財務データ取得中...'):
        metrics = fetch_fundamentals(selected_ticker)

    if not metrics:
        st.error('財務データが取得できませんでした。')
        return

    # 評価
    evals = evaluate_buy_rules(metrics)

    # 表を作成して表示（買いルールのみ）
    for section, checks in evals.items():
        display_title = section_title_map.get(section, section)
        st.markdown(f"**{display_title}**")
        rows = []
        for k, v in checks.items():
            val = v
            metric_display = ''
            # 表示用の実数値を補足
            try:
                if '自己資本比率' in k:
                    metric_display = fmt_percent(metrics.get('equityRatio'), precision=2)
                if '有利子負債' in k:
                    td = metrics.get('totalDebt')
                    te = metrics.get('totalEquity')
                    try:
                        if td is not None and te is not None and te != 0:
                            metric_display = fmt_num(td / te, precision=2)
                        else:
                            metric_display = 'N/A'
                    except Exception:
                        metric_display = 'N/A'
                if 'EPS' in k:
                    metric_display = fmt_num(metrics.get('eps'), 2)
                if '経常利益成長率' in k or '売上高成長率' in k:
                    key = 'operatingIncomeGrowth' if '経常利益' in k else 'revenueGrowth'
                    metric_display = fmt_percent(metrics.get(key), precision=1)
                if '営業利益率' in k:
                    metric_display = fmt_percent(metrics.get('operatingMargin'), precision=1)
                if 'ROE' in k:
                    metric_display = fmt_percent(metrics.get('ROE'), precision=1)
                if 'PER' in k:
                    metric_display = fmt_num(metrics.get('PER'), precision=2)
                if '時価総額' in k:
                    metric_display = fmt_money(metrics.get('marketCap'))
            except Exception:
                metric_display = 'N/A'

            rows.append({
                '判定項目': k,
                '達成': '✅' if val else '❌',
                '値': metric_display
            })

        df_checks = pd.DataFrame(rows)
        st.dataframe(df_checks, use_container_width=True)

    # 最終ジャッジ（単純まとめ）
    final_buy = any(all(v for v in checks.values()) for checks in evals.values())
    if final_buy:
        st.success('総合判定: 買っても良い可能性があります（基準を満たすカテゴリあり）')
    else:
        st.info('総合判定: すぐに買う条件は満たしていません。追加確認を推奨します。')



def render_promising_stocks() -> None:
    """
    有力IPO銘柄一覧を表示
    """
    st.subheader("🚀 有力IPO銘柄の一覧")

    st.write(
        "以下は、"
        "① 公募価格割れ、"
        "② 時価総額30〜700億円、"
        "③ オーナー創業社長、"
        "といった条件を満たす銘柄です。"
    )

    service = IPOStockService()

    # failed tickers のサマリ表示と再試行ボタン
    try:
        failed_list = service.get_failed_tickers()
    except Exception:
        failed_list = []

    if failed_list:
        st.info(f"⏭ スキップ中の銘柄: {len(failed_list)}件があります。")
        with st.expander("スキップ銘柄一覧（クリックで展開）"):
            for tk in failed_list:
                st.write(tk)

        if st.button("スキップ解除して再試行"):
            with st.spinner("スキップ解除・再取得中..."):
                service.clear_failed_tickers()
                df = service.get_promising_ipos()
            st.session_state["promising_stocks_df"] = df
            st.success("再取得が完了しました。結果を表示します。")
            return

    # キャッシュの確認
    cached_df, cached_timestamp = service.load_cache()
    is_cache_valid = service.is_cache_valid(cached_timestamp)

    # キャッシュが存在する場合、選択肢を表示
    if cached_df is not None and not cached_df.empty:
        # キャッシュ情報の表示
        cache_date_str = cached_timestamp.strftime("%Y年%m月%d日 %H:%M")
        
        if is_cache_valid:
            st.info(f"💾 前回取得したデータ（{cache_date_str}）があります。")
        else:
            st.warning(f"⚠️ キャッシュデータ（{cache_date_str}）は有効期限切れです。")

        # ボタンを横並びに配置
        col1, col2 = st.columns(2)

        with col1:
            use_cache = st.button(
                "📂 前回のデータを表示",
                use_container_width=True,
                type="secondary"
            )

        with col2:
            fetch_new = st.button(
                "🔄 新しく取得する",
                use_container_width=True,
                type="primary"
            )

        # キャッシュを使う場合
        if use_cache:
            st.session_state["promising_stocks_df"] = cached_df
            st.success(f"前回のデータを表示しました（取得日時: {cache_date_str}）")

        # 新規取得する場合
        elif fetch_new:
            with st.spinner("有力銘柄を取得中..."):
                df = service.get_promising_ipos()
            st.session_state["promising_stocks_df"] = df
            st.success("最新のデータを取得しました！")

    else:
        # キャッシュがない場合、初回取得ボタン
        if st.button("🚀 有力銘柄を抽出する", type="primary"):
            with st.spinner("有力銘柄を取得中..."):
                df = service.get_promising_ipos()
            st.session_state["promising_stocks_df"] = df
            st.success("データの取得が完了しました！")

    # 結果表示
    if "promising_stocks_df" in st.session_state:
        df = st.session_state["promising_stocks_df"]

        if df.empty:
            st.info("条件に合致する銘柄は見つかりませんでした。")
        else:
            st.write(f"**該当銘柄数: {len(df)}件**")
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
            )

            st.caption(
                "※ 本情報は投資助言ではありません。最終判断はご自身で行ってください。"
            )


def fetch_stock_data(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """
    yfinanceで株価データを取得
    """
    df = yf.download(ticker, period=period, interval=interval, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()

    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['Open', 'High', 'Low', 'Close', 'Volume'])

    df.index.name = 'Date'
    return df


def create_candlestick_chart(ticker: str, period: str, interval: str, title_dict: dict = None):
    """
    Plotlyで単一銘柄のインタラクティブなローソク足チャートを作成
    """
    try:
        df = fetch_stock_data(ticker, period, interval)
        
        if df.empty:
            return None
        
        # 銘柄名辞書が渡されない場合はTITLE_DICTを使用（後方互換）
        if title_dict is None:
            title_dict = TITLE_DICT
        title_jp = title_dict.get(ticker, ticker)
        
        # サブプロット作成（価格チャートと出来高）
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.7, 0.3],
            subplot_titles=(f'{title_jp} ({ticker})', '出来高')
        )
        
        # ローソク足チャート
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='価格'
            ),
            row=1, col=1
        )
        
        # 出来高
        colors = ['red' if close < open else 'green' 
                  for close, open in zip(df['Close'], df['Open'])]
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df['Volume'],
                name='出来高',
                marker_color=colors,
                showlegend=False
            ),
            row=2, col=1
        )
        
        # レイアウト設定
        fig.update_layout(
            height=600,
            xaxis_rangeslider_visible=False,
            hovermode='x unified',
            template='plotly_white'
        )
        
        fig.update_xaxes(title_text="日付", row=2, col=1)
        fig.update_yaxes(title_text="価格 (円)", row=1, col=1)
        fig.update_yaxes(title_text="出来高", row=2, col=1)
        
        return fig
        
    except Exception as e:
        return None


def create_mini_chart(ticker: str, df: pd.DataFrame, title_dict: dict = None) -> go.Figure:
    """
    グリッド表示用のミニチャートを作成
    """
    if title_dict is None:
        title_dict = TITLE_DICT
    title_jp = title_dict.get(ticker, ticker)
    
    fig = go.Figure()
    
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            showlegend=False
        )
    )
    
    fig.update_layout(
        title=title_jp,
        height=300,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_rangeslider_visible=False,
        template='plotly_white'
    )
    
    return fig


def render_chart_page() -> None:
    """
    インタラクティブなチャート表示ページ
    """
    st.title("📊 チャートの表示")
    st.write("銘柄のローソク足チャートをインタラクティブに表示します。")
    
    # サイドバーから選択された区分に応じて銘柄リストを取得
    position = st.session_state.get("sidebar_position", "保有株")
    tickers, title_dict = get_tickers_and_names(position)
    
    if not tickers:
        st.warning("銘柄データが読み込めませんでした。")
        return
    
    # サイドバーから期間設定を取得し、足種を自動判定
    period_map = {
        "3ヶ月": "3mo",
        "半年": "6mo",
        "1年": "1y",
        "3年": "3y"
    }
    period_label = st.session_state.get("sidebar_period", "3ヶ月")
    period = period_map.get(period_label, "3mo")
    
    # 期間によって足種を自動設定
    if period in ["3mo", "6mo"]:
        interval = "1d"  # 日足
    else:
        interval = "1wk"  # 週足
    
    # 表示モード選択（省スペース） — デフォルトを一覧表示(グリッド)にし、順序を入れ替え
    chart_options = ["一覧表示（グリッド）", "個別表示（タブ）"]
    display_mode_index = 0 if "display_mode" not in st.session_state else (chart_options.index(st.session_state.get("display_mode")) if st.session_state.get("display_mode") in chart_options else 0)
    display_mode = st.radio(
        "表示モード",
        options=chart_options,
        index=display_mode_index,
        horizontal=True,
        key="display_mode"
    )
    
    # st.caption(f"📊 期間: {period_label} / 足種: {interval_label}")
    st.divider()
    
    # データ取得とキャッシュ
    @st.cache_data(ttl=300)  # 5分間キャッシュ
    def load_all_data(tickers: list, period: str, interval: str):
        data = {}
        for ticker in tickers:
            try:
                df = fetch_stock_data(ticker, period, interval)
                if not df.empty:
                    data[ticker] = df
            except:
                continue
        return data
    
    with st.spinner("データを取得中..."):
        all_data = load_all_data(tickers, period, interval)
    
    if not all_data:
        st.error("データの取得に失敗しました。")
        return
    
    # 表示モードによって切り替え
    if display_mode == "個別表示（タブ）":
        # タブで個別表示
        tabs = st.tabs([title_dict.get(ticker, ticker) for ticker in tickers if ticker in all_data])
        
        for idx, ticker in enumerate([t for t in tickers if t in all_data]):
            with tabs[idx]:
                fig = create_candlestick_chart(ticker, period, interval, title_dict)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 統計情報表示
                    df = all_data[ticker]
                    col_a, col_b, col_c, col_d = st.columns(4)
                    with col_a:
                        st.metric("最新価格", f"{df['Close'].iloc[-1]:.2f}円")
                    with col_b:
                        change = df['Close'].iloc[-1] - df['Close'].iloc[0]
                        st.metric("期間変動", f"{change:.2f}円", 
                                 delta=f"{(change/df['Close'].iloc[0]*100):.2f}%")
                    with col_c:
                        st.metric("最高値", f"{df['High'].max():.2f}円")
                    with col_d:
                        st.metric("最安値", f"{df['Low'].min():.2f}円")
                else:
                    st.error(f"{ticker}のチャートを表示できませんでした。")
    
    else:
        # グリッド表示（2列）
        # st.info("💡 各チャートをクリックすると拡大できます。")
        cols_per_row = 2
        
        tickers_with_data = [t for t in tickers if t in all_data]
        for i in range(0, len(tickers_with_data), cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                idx = i + j
                if idx < len(tickers_with_data):
                    ticker = tickers_with_data[idx]
                    with cols[j]:
                        fig = create_mini_chart(ticker, all_data[ticker], title_dict)
                        st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    st.caption("💡 チャートはインタラクティブです。ズーム、パン、ホバーで詳細情報を確認できます。")
    st.caption("📊 データはyfinanceから取得しています。")


def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    テクニカル指標を計算
    """
    close = df['Close'].squeeze()
    
    # 移動平均線
    df['SMA_5'] = ta.trend.SMAIndicator(close, window=5).sma_indicator()
    df['SMA_20'] = ta.trend.SMAIndicator(close, window=20).sma_indicator()
    
    # RSI
    df['RSI'] = ta.momentum.RSIIndicator(close, window=14).rsi()
    
    # MACD
    macd = ta.trend.MACD(close)
    df['MACD'] = macd.macd()
    df['MACD_signal'] = macd.macd_signal()
    
    # 买い/売りシグナル（移動平均のクロス）
    df['BuySignal'] = (df['SMA_5'] > df['SMA_20']) & (df['SMA_5'].shift(1) <= df['SMA_20'].shift(1))
    df['SellSignal'] = (df['SMA_5'] < df['SMA_20']) & (df['SMA_5'].shift(1) >= df['SMA_20'].shift(1))
    
    return df


def analyze_signals(df: pd.DataFrame) -> tuple:
    """
    最新のシグナルを分析
    """
    if len(df) < 2:
        return False, False, "データ不足"
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    buy_signal = False
    sell_signal = False
    comments = []
    
    # MACDクロス判定
    macd_diff = latest['MACD'] - latest['MACD_signal']
    prev_macd_diff = prev['MACD'] - prev['MACD_signal']
    
    macd_golden = (macd_diff > 0) and (prev_macd_diff <= 0)
    macd_dead = (macd_diff < 0) and (prev_macd_diff >= 0)
    
    rsi_val = latest['RSI']
    
    # ✅ 買い時条件
    if rsi_val < 30 and macd_golden:
        buy_signal = True
        comments.append("✅ 買い時サイン: RSI売られすぎ & MACDゴールデンクロス")
    
    # ❌ 売り時条件
    if rsi_val > 70 and macd_dead:
        sell_signal = True
        comments.append("❌ 売り時サイン: RSI買われすぎ & MACDデッドクロス")
    
    # 補助コメント
    if not buy_signal and not sell_signal:
        if rsi_val < 30:
            comments.append("🔵 RSI<30: 売られすぎだが、まだ転換シグナルなし")
        elif rsi_val > 70:
            comments.append("🔴 RSI>70: 買われすぎだが、まだ反落シグナルなし")
        else:
            comments.append(f"⚪ RSI={rsi_val:.1f}: 中立圧")
    
    return buy_signal, sell_signal, " / ".join(comments)


def create_trend_chart(df: pd.DataFrame, ticker: str, comment_text: str, title_dict: dict = None) -> go.Figure:
    """
    テクニカル分析チャートを作成
    """
    fig = go.Figure()
    
    # ローソク足
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name="価格"
    ))
    
    # SMA
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['SMA_5'],
        mode='lines',
        name='SMA 5',
        line=dict(color='orange', width=1)
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['SMA_20'],
        mode='lines',
        name='SMA 20',
        line=dict(color='blue', width=1)
    ))
    
    # 買いシグナル
    buy_dates = df.index[df['BuySignal']]
    buy_prices = df['Close'][df['BuySignal']]
    if len(buy_dates) > 0:
        fig.add_trace(go.Scatter(
            x=buy_dates,
            y=buy_prices,
            mode='markers',
            marker=dict(color='green', size=12, symbol='triangle-up'),
            name='買いシグナル'
        ))
    
    # 売りシグナル
    sell_dates = df.index[df['SellSignal']]
    sell_prices = df['Close'][df['SellSignal']]
    if len(sell_dates) > 0:
        fig.add_trace(go.Scatter(
            x=sell_dates,
            y=sell_prices,
            mode='markers',
            marker=dict(color='red', size=12, symbol='triangle-down'),
            name='売りシグナル'
        ))
    
    # コメント追加
    fig.add_annotation(
        text=comment_text,
        xref="paper", yref="paper",
        x=0.01, y=-0.15,
        showarrow=False,
        align="left",
        font=dict(size=11),
        bordercolor="gray",
        borderwidth=1,
        borderpad=5,
        bgcolor="white"
    )
    
    if title_dict is None:
        title_dict = TITLE_DICT
    title_jp = title_dict.get(ticker, ticker)
    fig.update_layout(
        title=f"{title_jp} ({ticker}) 株価とテクニカル分析",
        xaxis_rangeslider_visible=False,
        height=550,
        margin=dict(t=50, b=120, l=50, r=50),
        template='plotly_white',
        hovermode='x unified'
    )
    
    return fig


def render_trend_analysis_page() -> None:
    """
    傾向分析ページ
    """
    st.title("📉 傾向分析")
    st.write("テクニカル指標（SMA, RSI, MACD）を使って買い/売りシグナルを分析します。")
    
    # サイドバーから選択された区分に応じて銘柄リストを取得
    position = st.session_state.get("sidebar_position", "保有株")
    tickers, title_dict = get_tickers_and_names(position)
    
    if not tickers:
        st.warning("銘柄データが読み込めませんでした。")
        return
    
    # サイドバーから期間設定を取得し、足種を自動判定
    period_map = {
        "3ヶ月": "3mo",
        "半年": "6mo",
        "1年": "1y",
        "3年": "3y"
    }
    period_label = st.session_state.get("sidebar_period", "3ヶ月")
    period = period_map.get(period_label, "3mo")
    
    # 期間によって足種を自動設定
    if period in ["3mo", "6mo"]:
        interval = "1d"  # 日足
    else:
        interval = "1wk"  # 週足
    
    # 表示モード選択（省スペース） — デフォルトを一覧表示(縦並び)にし、順序を入れ替え
    trend_options = ["一覧表示（縦並び）", "個別表示（タブ）"]
    trend_mode_index = 0 if "trend_display_mode" not in st.session_state else (trend_options.index(st.session_state.get("trend_display_mode")) if st.session_state.get("trend_display_mode") in trend_options else 0)
    display_mode = st.radio(
        "表示モード",
        options=trend_options,
        index=trend_mode_index,
        horizontal=True,
        key="trend_display_mode"
    )
    
    # st.caption(f"📊 期間: {period_label} / 足種: {interval_label}")
    st.divider()
    
    # データ取得と分析
    @st.cache_data(ttl=300)
    def load_and_analyze_data(tickers: list, period: str, interval: str):
        results = {}
        for ticker in tickers:
            try:
                df = fetch_stock_data(ticker, period, interval)
                if not df.empty and len(df) >= 20:  # 最低20日分のデータが必要
                    df = calculate_technical_indicators(df)
                    buy_signal, sell_signal, comment = analyze_signals(df)
                    results[ticker] = {
                        'df': df,
                        'buy_signal': buy_signal,
                        'sell_signal': sell_signal,
                        'comment': comment
                    }
            except Exception as e:
                continue
        return results
    
    with st.spinner("テクニカル分析中..."):
        analysis_results = load_and_analyze_data(tickers, period, interval)
    
    if not analysis_results:
        st.error("データの取得に失敗しました。")
        return
    
    # シグナルサマリー表示
    buy_count = sum(1 for r in analysis_results.values() if r['buy_signal'])
    sell_count = sum(1 for r in analysis_results.values() if r['sell_signal'])
    neutral_count = len(analysis_results) - buy_count - sell_count
    
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("🟢 買いシグナル", f"{buy_count}銘柄")
    with col_b:
        st.metric("🔴 売りシグナル", f"{sell_count}銘柄")
    with col_c:
        st.metric("⚪ 中立", f"{neutral_count}銘柄")
    
    st.divider()
    
    # 表示モード別の描画
    if display_mode == "個別表示（タブ）":
        tabs = st.tabs([title_dict.get(ticker, ticker) for ticker in tickers if ticker in analysis_results])
        
        for idx, ticker in enumerate([t for t in tickers if t in analysis_results]):
            with tabs[idx]:
                result = analysis_results[ticker]
                fig = create_trend_chart(result['df'], ticker, result['comment'], title_dict)
                st.plotly_chart(fig, use_container_width=True)
                
                # シグナル表示
                if result['buy_signal']:
                    st.success("🟢 買いシグナル検出")
                elif result['sell_signal']:
                    st.error("🔴 売りシグナル検出")
                else:
                    st.info("⚪ 中立（明確なシグナルなし）")
                
                st.caption(result['comment'])
    else:
        # 一覧表示
        for ticker in tickers:
            if ticker in analysis_results:
                result = analysis_results[ticker]
                title_jp = title_dict.get(ticker, ticker)
                
                st.subheader(f"{title_jp} ({ticker})")
                fig = create_trend_chart(result['df'], ticker, result['comment'], title_dict)
                st.plotly_chart(fig, use_container_width=True)
                
                if result['buy_signal']:
                    st.success("🟢 買いシグナル検出")
                elif result['sell_signal']:
                    st.error("🔴 売りシグナル検出")
                else:
                    st.info("⚪ 中立（明確なシグナルなし）")
                
                st.divider()
    
    st.caption("💡 SMA5がSMA20を上抜けると買いシグナル、下抜けると売りシグナルと判定します。")
    st.caption("⚠️ この分析は参考情報です。最終的な投資判断はご自身の責任で行ってください。")
