import json
from pathlib import Path
import requests
import yfinance as yf

STOCKS_PATH = Path(__file__).parent / "stocks.json"


def load_stocks():
    if not STOCKS_PATH.exists():
        return {"保有株": {"tickers": [], "names": {}}, "注目株": {"tickers": [], "names": {}}}
    with open(STOCKS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_stocks(data):
    with open(STOCKS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_code(code: str) -> str:
    code = code.strip()
    if "." in code:
        return code
    # assume Tokyo market
    if code.endswith("T"):
        return code
    return code.zfill(4) + ".T"


def lookup_by_name(data, name_query: str):
    q = name_query.lower()
    results = []
    for section in ["保有株", "注目株"]:
        names = data.get(section, {}).get("names", {})
        for tk, nm in names.items():
            if q in nm.lower():
                results.append((tk, nm, section))
    return results


def yahoo_search(query: str, limit: int = 10):
    """Yahoo Finance の検索APIを使って候補を取得する（best-effort）。
    戻り値: list of (symbol, name)
    """
    try:
        url = (
            f"https://query2.finance.yahoo.com/v1/finance/search?q={requests.utils.requote_uri(query)}"
            f"&quotesCount={limit}&newsCount=0"
        )
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=8)
        r.raise_for_status()
        j = r.json()
        quotes = j.get("quotes", [])
        out = []
        for q in quotes:
            sym = q.get("symbol")
            name = q.get("shortname") or q.get("longname") or q.get("name")
            if sym and name:
                out.append((sym, name))
        return out
    except Exception:
        # フォールバック1: finance.yahoo.com の lookup ページをスクレイピング
        try:
            lookup_url = f"https://finance.yahoo.com/lookup?s={requests.utils.requote_uri(query)}"
            headers = {"User-Agent": "Mozilla/5.0"}
            r2 = requests.get(lookup_url, headers=headers, timeout=8)
            r2.raise_for_status()
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(r2.text, "html.parser")
            out = []
            # 検索結果のテーブルを探す
            table = soup.find("table")
            if table:
                for tr in table.find_all("tr")[1:limit+1]:
                    tds = tr.find_all("td")
                    if len(tds) >= 2:
                        sym = tds[0].get_text(strip=True)
                        name = tds[1].get_text(strip=True)
                        if sym and name:
                            out.append((sym, name))
            if out:
                return out
        except Exception:
            pass

        # フォールバック2: finance.yahoo.co.jp（日本版）の検索結果ページから抽出
        try:
            lookup_jp = f"https://finance.yahoo.co.jp/search/?query={requests.utils.requote_uri(query)}"
            headers = {"User-Agent": "Mozilla/5.0"}
            r3 = requests.get(lookup_jp, headers=headers, timeout=8)
            r3.raise_for_status()
            # 日本語ページはエンコーディング推測を明示しておく
            try:
                r3.encoding = r3.apparent_encoding or 'utf-8'
            except Exception:
                r3.encoding = 'utf-8'
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(r3.text, "html.parser")
            out = []
            # 検索結果は <div id="sr" class="SearchList..."> 以下の list items に入っている
            sr = soup.find(id="sr")
            if sr:
                for li in sr.find_all("li", limit=limit):
                    # リンク先に /quote/<code>.T が付いている
                    a = li.find("a", href=True)
                    if not a:
                        continue
                    href = a["href"]
                    # href から銘柄コードを抽出
                    import re

                    m = re.search(r"/quote/(\d+)(?:\.T)?", href)
                    if m:
                        code = m.group(1)
                        sym = code + ".T"
                    else:
                        # サポート要素から探す（li 要素に code がある場合）
                        supp = li.find("li")
                        sym = None
                        if supp:
                            txt = supp.get_text(strip=True)
                            if txt.isdigit():
                                sym = txt + ".T"
                    # 銘柄名を取得（UI要素やラベルが混ざるのでフィルタして最適候補を選ぶ）
                    texts = [s.strip() for s in a.stripped_strings]
                    # 補助ラベルや価格を除外するパターン
                    bad_labels = set([
                        'チャート', '時系列', 'ニュース', '企業情報', '掲示板', '株主優待',
                        '板', '出来高', '前日比', '始値', '高値', '安値', '終値'
                    ])
                    import re

                    def is_price_token(t):
                        return bool(re.match(r'^[\d,]+(?:\.\d+)?$', t)) or '円' in t

                    candidate = None
                    for t in texts:
                        if not t:
                            continue
                        if t in bad_labels:
                            continue
                        if is_price_token(t):
                            continue
                        # 排除: 単純なコード表記や短すぎるトークン
                        if t.isdigit() and len(t) <= 4:
                            continue
                        if len(t) <= 1:
                            continue
                        candidate = t
                        break

                    # それでも見つからなければ、li 要素全体のテキストから長めのトークンを拾う
                    if not candidate:
                        all_text = li.get_text(" ", strip=True)
                        parts = [p.strip() for p in re.split(r'[\s\|/]', all_text) if p.strip()]
                        for p in parts:
                            if is_price_token(p) or p in bad_labels:
                                continue
                            if re.search(r'[\u3040-\u30ff\u4e00-\u9fff]', p) or re.search(r'[A-Za-z]', p):
                                if len(p) > 2:
                                    candidate = p
                                    break

                    if sym and candidate:
                        out.append((sym, candidate))
            # 重複を削って返す（同一シンボルは一つだけ）
            seen = set()
            uniq = []
            for s, n in out:
                if s in seen:
                    continue
                seen.add(s)
                uniq.append((s, n))

            # 補完: 可能なら yfinance から正式名を取得して表示名を上書きする
            try:
                import yfinance as yf
                improved = []
                for s, n in uniq:
                    real_name = None
                    try:
                        tk = yf.Ticker(s)
                        info = tk.info or {}
                        real_name = info.get('shortName') or info.get('longName')
                    except Exception:
                        real_name = None
                    improved.append((s, real_name or n))
                return improved
            except Exception:
                return uniq
        except Exception:
            return []


def confirm(prompt: str) -> bool:
    ans = input(prompt + " [y/N]: ").strip().lower()
    return ans == "y" or ans == "yes"


def add_flow(data):
    print("追加: 銘柄で指定するか、証券コードで指定するか選んでください")
    mode = input("1: 銘柄名で検索  2: 証券コード指定 > ").strip()
    chosen = None

    if mode == "1":
        q = input("銘柄名の一部を入力: ").strip()
        matches = lookup_by_name(data, q)
        if matches:
            print("候補:")
            for i, (tk, nm, sec) in enumerate(matches, 1):
                print(f"{i}. {nm} ({tk}) [{sec}]")
            sel = input("追加する候補番号を入力（0でキャンセル）: ").strip()
            if sel.isdigit() and int(sel) > 0 and int(sel) <= len(matches):
                chosen = matches[int(sel) - 1][0]
            else:
                print("キャンセルまたは無効な選択")
                return
        else:
                # local search にヒットなし。まず Yahoo 検索で候補を探す
                print("候補が見つかりません。外部検索を試します...")
                yres = yahoo_search(q, limit=10)
                if yres:
                    print("外部候補:")
                    for i, (sym, nm) in enumerate(yres, 1):
                        print(f"{i}. {nm} ({sym})")
                    sel = input("候補番号を入力（0: キャンセル / または Enter で直接コード入力）: ").strip()
                    if sel.isdigit() and int(sel) > 0 and int(sel) <= len(yres):
                        chosen = yres[int(sel) - 1][0]
                    else:
                        code = input("証券コード（例 7203 または 7203.T、未入力で中止）: ").strip()
                        if not code:
                            print("入力がありません。追加を中止します。")
                            return
                        chosen = normalize_code(code)
                else:
                    print("外部候補も見つかりませんでした。証券コードで指定してください。")
                    code = input("証券コード（例 7203 または 7203.T、未入力で中止）: ").strip()
                    if not code:
                        print("入力がありません。追加を中止します。")
                        return
                    chosen = normalize_code(code)
    else:
        code = input("証券コード（例 7203 または 7203.T）: ").strip()
        chosen = normalize_code(code)

    # try to fetch name via yfinance if not present
    name = None
    for sec in ["保有株", "注目株"]:
        if chosen in data.get(sec, {}).get("tickers", []):
            name = data[sec]["names"].get(chosen)
            print(f"{chosen} は既に {sec} に存在: {name}")
            return

    try:
        tk = yf.Ticker(chosen)
        info = tk.info or {}
        name = info.get("shortName") or info.get("longName")
    except Exception:
        name = None

    display_name = name or input("表示名が見つかりません。表示名を入力してください（例: トヨタ自動車）: ").strip()
    print(f"追加候補: {display_name} ({chosen})")
    if not confirm("追加してよいですか？"):
        print("追加を中止しました")
        return

    # 選ぶカテゴリ
    cat = input("追加先を選んでください 1: 保有株 2: 注目株 > ").strip()
    target = "保有株" if cat == "1" else "注目株"

    # insert
    if chosen not in data[target]["tickers"]:
        data[target]["tickers"].append(chosen)
    data[target]["names"][chosen] = display_name
    save_stocks(data)
    print(f"{display_name} ({chosen}) を {target} に追加しました")


def delete_flow(data):
    cat = input("削除対象を選択 1: 保有株 2: 注目株 > ").strip()
    target = "保有株" if cat == "1" else "注目株"
    tickers = data.get(target, {}).get("tickers", [])
    if not tickers:
        print("対象リストが空です")
        return
    print(f"{target} の銘柄:")
    for i, tk in enumerate(tickers, 1):
        nm = data[target]["names"].get(tk, "-")
        print(f"{i}. {nm} ({tk})")
    sel = input("削除する番号をカンマ区切りで入力（例: 1,3）または 0 でキャンセル > ").strip()
    if sel == "0":
        print("キャンセル")
        return
    indices = [s.strip() for s in sel.split(",") if s.strip().isdigit()]
    to_remove = []
    for idx in indices:
        i = int(idx) - 1
        if 0 <= i < len(tickers):
            to_remove.append(tickers[i])
    if not to_remove:
        print("有効な選択がありません")
        return
    print("次の銘柄を削除します:")
    for tk in to_remove:
        print(f"- {data[target]['names'].get(tk,'-')} ({tk})")
    if not confirm("本当に削除しますか？"):
        print("削除を中止しました")
        return
    for tk in to_remove:
        if tk in data[target]["tickers"]:
            data[target]["tickers"].remove(tk)
        if tk in data[target]["names"]:
            del data[target]["names"][tk]
    save_stocks(data)
    print("削除が完了しました")


def edit_flow(data):
    cat = input("編集対象を選択 1: 保有株 2: 注目株 > ").strip()
    target = "保有株" if cat == "1" else "注目株"
    tickers = data.get(target, {}).get("tickers", [])
    if not tickers:
        print("対象リストが空です")
        return
    print(f"{target} の銘柄:")
    for i, tk in enumerate(tickers, 1):
        nm = data[target]["names"].get(tk, "-")
        print(f"{i}. {nm} ({tk})")
    sel = input("編集する銘柄の番号を入力（0でキャンセル） > ").strip()
    if not sel.isdigit() or sel == "0":
        print("キャンセルまたは無効")
        return
    idx = int(sel) - 1
    if not (0 <= idx < len(tickers)):
        print("範囲外です")
        return
    tk = tickers[idx]
    print(f"選択: {data[target]['names'].get(tk,'-')} ({tk})")
    action = input("1: 表示名を変更 2: 他カテゴリへ移動 > ").strip()
    if action == "1":
        new_name = input("新しい表示名を入力: ").strip()
        if new_name:
            data[target]["names"][tk] = new_name
            save_stocks(data)
            print("表示名を更新しました")
    else:
        other = "注目株" if target == "保有株" else "保有株"
        # remove from current
        data[target]["tickers"].remove(tk)
        # add to other
        if tk not in data[other]["tickers"]:
            data[other]["tickers"].append(tk)
        # move name mapping
        nm = data[target]["names"].pop(tk, None)
        if nm:
            data[other]["names"][tk] = nm
        save_stocks(data)
        print(f"{tk} を {other} に移動しました")


def main():
    data = load_stocks()
    while True:
        print('\n=== stocks.json メンテナンス ===')
        print('1. 追加')
        print('2. 削除')
        print('3. 編集')
        print('0. 終了')
        choice = input('選択 > ').strip()
        if choice == '1':
            add_flow(data)
            data = load_stocks()
        elif choice == '2':
            delete_flow(data)
            data = load_stocks()
        elif choice == '3':
            edit_flow(data)
            data = load_stocks()
        elif choice == '0':
            print('終了')
            break
        else:
            print('無効な選択です')


if __name__ == '__main__':
    main()
