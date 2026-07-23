"""백테스트 결과 → 자체 완결형 HTML 리포트.

외부 라이브러리/CDN 없이 인라인 SVG로 수익곡선을 그리고,
요약 통계 카드와 매매 내역 표를 렌더링한다. 라이트/다크 테마 모두 지원.
"""
from __future__ import annotations

import html

from autotrader.backtest import BacktestResult


def _sparkline_svg(values: list[float], width: int = 820, height: int = 260) -> str:
    """평가금액 곡선을 SVG 선그래프로 렌더링."""
    if len(values) < 2:
        return '<p class="muted">데이터가 부족합니다.</p>'

    pad = 8
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    n = len(values)

    def x(i: int) -> float:
        return pad + i * (width - 2 * pad) / (n - 1)

    def y(v: float) -> float:
        return pad + (1 - (v - lo) / span) * (height - 2 * pad)

    pts = [(x(i), y(v)) for i, v in enumerate(values)]
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    # 시작 자본선(기준선) 위치
    base = values[0]
    base_y = y(base)
    area = (
        f"M {pts[0][0]:.1f},{height - pad:.1f} "
        + " ".join(f"L {px:.1f},{py:.1f}" for px, py in pts)
        + f" L {pts[-1][0]:.1f},{height - pad:.1f} Z"
    )
    up = values[-1] >= base
    stroke = "#16a34a" if up else "#dc2626"
    fill = "url(#gGreen)" if up else "url(#gRed)"

    return f"""<svg viewBox="0 0 {width} {height}" width="100%" preserveAspectRatio="none" role="img" aria-label="평가금액 곡선">
  <defs>
    <linearGradient id="gGreen" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#16a34a" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="#16a34a" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="gRed" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#dc2626" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="#dc2626" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <line x1="{pad}" y1="{base_y:.1f}" x2="{width - pad}" y2="{base_y:.1f}"
        stroke="currentColor" stroke-opacity="0.25" stroke-dasharray="4 4"/>
  <path d="{area}" fill="{fill}" stroke="none"/>
  <polyline points="{line}" fill="none" stroke="{stroke}" stroke-width="2"
            stroke-linejoin="round" stroke-linecap="round"/>
</svg>"""


def _stat_card(label: str, value: str, tone: str = "") -> str:
    return (
        f'<div class="card"><div class="card-label">{html.escape(label)}</div>'
        f'<div class="card-value {tone}">{html.escape(value)}</div></div>'
    )


def _trades_table(result: BacktestResult, limit: int = 200) -> str:
    rows = []
    for t in result.trades[:limit]:
        is_buy = t.action.startswith("BUY")
        tone = "buy" if is_buy else "sell"
        rows.append(
            f"<tr><td><span class='pill {tone}'>{html.escape(t.action)}</span></td>"
            f"<td>{html.escape(t.symbol)}</td>"
            f"<td class='num'>{t.quantity}</td>"
            f"<td class='num'>{t.price:,.0f}</td>"
            f"<td class='reason'>{html.escape(t.reason)}</td></tr>"
        )
    more = ""
    if len(result.trades) > limit:
        more = f"<p class='muted'>… 외 {len(result.trades) - limit}건 생략</p>"
    body = "\n".join(rows) or "<tr><td colspan='5' class='muted'>매매 없음</td></tr>"
    return f"""<table>
  <thead><tr><th>구분</th><th>종목</th><th>수량</th><th>체결가</th><th>사유</th></tr></thead>
  <tbody>{body}</tbody>
</table>{more}"""


def render_html(result: BacktestResult, title: str = "AIbot 백테스트 리포트") -> str:
    ret = result.total_return_pct
    ret_tone = "pos" if ret >= 0 else "neg"
    cards = "".join([
        _stat_card("총 수익률", f"{ret:+.2f}%", ret_tone),
        _stat_card("최종 평가금액", f"{result.end_equity:,.0f}"),
        _stat_card("시작 자본", f"{result.start_equity:,.0f}"),
        _stat_card("승률", f"{result.win_rate_pct:.0f}%"),
        _stat_card("최대 낙폭(MDD)", f"-{result.max_drawdown_pct:.2f}%", "neg" if result.max_drawdown_pct else ""),
        _stat_card("매매 사이클", f"{result.num_round_trips}회"),
        _stat_card("총 체결", f"{len(result.trades)}건"),
    ])
    chart = _sparkline_svg(result.equity_curve)
    table = _trades_table(result)
    esc_title = html.escape(title)

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{esc_title}</title>
<style>
  :root {{
    --bg:#f7f8fa; --panel:#ffffff; --text:#1a1d23; --muted:#6b7280;
    --border:#e5e7eb; --pos:#16a34a; --neg:#dc2626;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#0f1115; --panel:#171a21; --text:#e6e8eb; --muted:#9aa1ab;
      --border:#262b34; --pos:#22c55e; --neg:#ef4444;
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;
    line-height:1.5; }}
  .wrap {{ max-width:900px; margin:0 auto; padding:28px 20px 60px; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  .sub {{ color:var(--muted); font-size:13px; margin:0 0 22px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:12px; margin-bottom:22px; }}
  .card {{ background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:14px 16px; }}
  .card-label {{ font-size:12px; color:var(--muted); margin-bottom:6px; }}
  .card-value {{ font-size:20px; font-weight:650; font-variant-numeric:tabular-nums; }}
  .pos {{ color:var(--pos); }} .neg {{ color:var(--neg); }}
  .panel {{ background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:16px; margin-bottom:22px; color:var(--text); }}
  .panel h2 {{ font-size:14px; margin:0 0 12px; color:var(--muted); font-weight:600; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--border); }}
  th {{ color:var(--muted); font-weight:600; font-size:12px; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td.reason {{ color:var(--muted); font-size:12px; }}
  .pill {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:600; }}
  .pill.buy {{ background:rgba(22,163,74,0.15); color:var(--pos); }}
  .pill.sell {{ background:rgba(220,38,38,0.15); color:var(--neg); }}
  .muted {{ color:var(--muted); font-size:12px; }}
  .tablewrap {{ overflow-x:auto; }}
  .warn {{ font-size:12px; color:var(--muted); border-top:1px solid var(--border); padding-top:14px; }}
</style>
</head>
<body>
  <div class="wrap">
    <h1>{esc_title}</h1>
    <p class="sub">모의(PaperBroker) 시뮬레이션 결과 · 실제 투자 결과가 아닙니다</p>
    <div class="cards">{cards}</div>
    <div class="panel">
      <h2>평가금액 곡선</h2>
      <div style="color:var(--muted)">{chart}</div>
    </div>
    <div class="panel">
      <h2>매매 내역</h2>
      <div class="tablewrap">{table}</div>
    </div>
    <p class="warn">⚠️ 랜덤워크 기반 모의 데이터로 생성된 리포트입니다. 전략 로직 검증용이며,
    실제 수익을 보장하지 않습니다. 실계좌 연결 전 반드시 각 증권사 모의투자로 재검증하세요.</p>
  </div>
</body>
</html>"""


def write_report(result: BacktestResult, path: str, title: str = "AIbot 백테스트 리포트") -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html(result, title))
    return path
