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
        render_input_form(service)
        render_history()
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


def create_candlestick_chart(ticker: str, period: str, interval: str):
    """
    Plotlyで単一銘柄のインタラクティブなローソク足チャートを作成
    """
    try:
        df = fetch_stock_data(ticker, period, interval)
        
        if df.empty:
            return None
        
        title_jp = TITLE_DICT.get(ticker, ticker)
        
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


def create_mini_chart(ticker: str, df: pd.DataFrame) -> go.Figure:
    """
    グリッド表示用のミニチャートを作成
    """
    title_jp = TITLE_DICT.get(ticker, ticker)
    
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
    
    # 期間と足種の設定
    col1, col2, col3 = st.columns([2, 2, 2])
    
    with col1:
        # サイドバーから期間設定を取得
        period_map = {
            "3ヶ月": "3mo",
            "半年": "6mo",
            "1年": "1y",
            "3年": "3y"
        }
        period_label = st.session_state.get("sidebar_period", "3ヶ月")
        period = period_map.get(period_label, "3mo")
        st.info(f"📅 期間: {period_label}")
    
    with col2:
        interval = st.selectbox(
            "🕐 足種",
            options=["1d", "1wk", "1mo"],
            format_func=lambda x: {
                "1d": "日足",
                "1wk": "週足",
                "1mo": "月足"
            }[x],
            index=0,
            key="chart_interval"
        )
    
    with col3:
        display_mode = st.selectbox(
            "📱 表示モード",
            options=["個別表示（タブ）", "一覧表示（グリッド）"],
            index=0,
            key="display_mode"
        )
    
    st.divider()
    
    # データ取得とキャッシュ
    @st.cache_data(ttl=300)  # 5分間キャッシュ
    def load_all_data(period: str, interval: str):
        data = {}
        for ticker in TICKERS:
            try:
                df = fetch_stock_data(ticker, period, interval)
                if not df.empty:
                    data[ticker] = df
            except:
                continue
        return data
    
    with st.spinner("データを取得中..."):
        all_data = load_all_data(period, interval)
    
    if not all_data:
        st.error("データの取得に失敗しました。")
        return
    
    # 表示モードによって切り替え
    if display_mode == "個別表示（タブ）":
        # タブで個別表示
        tabs = st.tabs([TITLE_DICT.get(ticker, ticker) for ticker in TICKERS if ticker in all_data])
        
        for idx, ticker in enumerate([t for t in TICKERS if t in all_data]):
            with tabs[idx]:
                fig = create_candlestick_chart(ticker, period, interval)
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
        st.info("💡 各チャートをクリックすると拡大できます。")
        cols_per_row = 2
        
        tickers_with_data = [t for t in TICKERS if t in all_data]
        for i in range(0, len(tickers_with_data), cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                idx = i + j
                if idx < len(tickers_with_data):
                    ticker = tickers_with_data[idx]
                    with cols[j]:
                        fig = create_mini_chart(ticker, all_data[ticker])
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


def create_trend_chart(df: pd.DataFrame, ticker: str, comment_text: str) -> go.Figure:
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
    
    title_jp = TITLE_DICT.get(ticker, ticker)
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
    
    # 設定
    col1, col2, col3 = st.columns([2, 2, 2])
    
    with col1:
        period_map = {
            "3ヶ月": "3mo",
            "半年": "6mo",
            "1年": "1y",
            "3年": "3y"
        }
        period_label = st.session_state.get("sidebar_period", "3ヶ月")
        period = period_map.get(period_label, "3mo")
        st.info(f"📅 期間: {period_label}")
    
    with col2:
        interval = st.selectbox(
            "🕐 足種",
            options=["1d", "1wk"],
            format_func=lambda x: {
                "1d": "日足",
                "1wk": "週足"
            }[x],
            index=0,
            key="trend_interval"
        )
    
    with col3:
        display_mode = st.selectbox(
            "📱 表示モード",
            options=["個別表示（タブ）", "一覧表示（縦並び）"],
            index=0,
            key="trend_display_mode"
        )
    
    st.divider()
    
    # データ取得と分析
    @st.cache_data(ttl=300)
    def load_and_analyze_data(period: str, interval: str):
        results = {}
        for ticker in TICKERS:
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
        analysis_results = load_and_analyze_data(period, interval)
    
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
        tabs = st.tabs([TITLE_DICT.get(ticker, ticker) for ticker in TICKERS if ticker in analysis_results])
        
        for idx, ticker in enumerate([t for t in TICKERS if t in analysis_results]):
            with tabs[idx]:
                result = analysis_results[ticker]
                fig = create_trend_chart(result['df'], ticker, result['comment'])
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
        for ticker in TICKERS:
            if ticker in analysis_results:
                result = analysis_results[ticker]
                title_jp = TITLE_DICT.get(ticker, ticker)
                
                st.subheader(f"{title_jp} ({ticker})")
                fig = create_trend_chart(result['df'], ticker, result['comment'])
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
