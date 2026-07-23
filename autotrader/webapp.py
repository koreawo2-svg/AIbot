"""브라우저 대시보드(표준 라이브러리 전용).

실행:
    python -m autotrader.webapp          # http://127.0.0.1:8000
    python -m autotrader.webapp --port 9000

기능:
    - 데이터 소스 선택: 샘플(005930) / 랜덤워크 / CSV 업로드
    - 전략 파라미터를 화면에서 조절(목표가/익절/손절/수량/트레일링스톱 등)
    - 실행 → 수익곡선·통계·매매내역을 즉시 시각화
추가 패키지 설치가 필요 없다.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from autotrader.brokers.paper import PaperBroker
from autotrader.data_loader import load_close_series, parse_close_series
from autotrader.engine import TradingEngine
from autotrader.market_data import RandomWalkFeed
from autotrader.models import OrderType
from autotrader.scheduler import LiveTrader
from autotrader.service import build_rule, result_to_dict, run_backtest
from autotrader.strategy.rule_engine import RuleEngineStrategy

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SAMPLE_CSV = os.path.join(_REPO_ROOT, "data", "sample_005930.csv")


def _randomwalk_series(n: int = 200, start: float = 70000.0, seed: int = 7) -> list[float]:
    rng = random.Random(seed)
    price = start
    out = []
    for _ in range(n):
        price = max(1000.0, price * (1 + rng.uniform(-0.02, 0.021)))
        out.append(round(price, 2))
    return out


def _load_series(payload: dict) -> tuple[str, list[float]]:
    """요청 payload에서 (종목코드, 종가 시계열)을 만든다."""
    source = payload.get("source", "sample")
    symbol = (payload.get("symbol") or "005930").strip()

    if source == "csv":
        text = payload.get("csv_text", "")
        if not text.strip():
            raise ValueError("CSV 내용이 비어 있습니다.")
        _, closes = parse_close_series(text)
        return symbol, closes
    if source == "randomwalk":
        return symbol, _randomwalk_series()
    # 기본: 샘플
    _, closes = load_close_series(_SAMPLE_CSV)
    return symbol or "005930", closes


class LiveSession:
    """백그라운드 스레드에서 실시간(모의) 자동매매를 돌리고 상태를 공유한다."""

    MAX_TRADES = 200

    def __init__(self):
        self._lock = threading.Lock()
        self._trader: LiveTrader | None = None
        self._thread: threading.Thread | None = None
        self._reset()

    def _reset(self):
        self.equity_curve: list[float] = []
        self.trades: list[dict] = []
        self.positions: list[dict] = []
        self.tick = -1
        self.start_equity = 0.0
        self.running = False
        self.error: str | None = None

    def start(self, symbol: str, params: dict, interval: float, ticks: int, start_price: float):
        with self._lock:
            if self.running:
                return  # 이미 실행 중이면 무시
            self._reset()
            self.running = True

        # 랜덤워크 실시간 시세로 구성(무한대에 가까운 흐름)
        seed = int(time.time()) & 0xFFFF
        feed = RandomWalkFeed(start_prices={symbol: start_price}, volatility=0.012, seed=seed)
        broker = PaperBroker(feed=feed, cash=float(params.get("cash", 10_000_000)))
        rule = build_rule(symbol, [start_price], params)
        engine = TradingEngine(broker, RuleEngineStrategy([rule]), [symbol], OrderType.MARKET)

        def on_tick(snap):
            with self._lock:
                self.tick = snap.tick
                self.equity_curve.append(round(snap.equity, 2))
                self.positions = snap.positions
                for t in snap.trades:
                    self.trades.append({**t, "tick": snap.tick})
                if len(self.trades) > self.MAX_TRADES:
                    del self.trades[: len(self.trades) - self.MAX_TRADES]

        self._trader = LiveTrader(engine, broker, interval_sec=interval,
                                  on_tick=on_tick, sleep_fn=time.sleep)
        self.start_equity = broker.get_account().cash

        def run():
            try:
                self._trader.run(ticks)
            except Exception as exc:  # 스레드 내 오류 보존
                with self._lock:
                    self.error = str(exc)
            finally:
                with self._lock:
                    self.running = False

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._trader:
            self._trader.stop()

    def snapshot(self) -> dict:
        with self._lock:
            cur = self.equity_curve[-1] if self.equity_curve else self.start_equity
            ret = ((cur - self.start_equity) / self.start_equity * 100.0) if self.start_equity else 0.0
            return {
                "running": self.running,
                "tick": self.tick,
                "equity": round(cur, 2),
                "start_equity": round(self.start_equity, 2),
                "return_pct": round(ret, 2),
                "equity_curve": list(self.equity_curve),
                "positions": list(self.positions),
                "trades": list(reversed(self.trades[-40:])),  # 최신 우선
                "error": self.error,
            }


LIVE = LiveSession()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 콘솔 소음 줄이기
        pass

    def _send(self, code: int, body: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/live/state":
            body = json.dumps({"ok": True, **LIVE.snapshot()}).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/backtest":
                data = self._backtest(payload)
            elif self.path == "/api/optimize":
                data = self._optimize(payload)
            elif self.path == "/api/live/start":
                data = self._live_start(payload)
            elif self.path == "/api/live/stop":
                LIVE.stop()
                data = {"stopped": True}
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            body = json.dumps({"ok": True, **data}).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        except Exception as exc:  # 사용자에게 오류 메시지 전달
            body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
            self._send(400, body, "application/json; charset=utf-8")

    def _backtest(self, payload: dict) -> dict:
        symbol, closes = _load_series(payload)
        result = run_backtest({symbol: closes}, payload.get("params", {}))
        data = result_to_dict(result)
        data["symbol"] = symbol
        data["points"] = len(closes)
        return data

    def _live_start(self, payload: dict) -> dict:
        symbol = (payload.get("symbol") or "005930").strip()
        params = payload.get("params", {})
        interval = float(payload.get("interval", 0.5))
        ticks = int(payload.get("ticks", 240))
        start_price = float(payload.get("start_price", params.get("target") or 70000))
        LIVE.start(symbol, params, interval, ticks, start_price)
        return {"started": True}

    def _optimize(self, payload: dict) -> dict:
        from autotrader.optimizer import optimize

        symbol, closes = _load_series(payload)
        grid = payload.get("grid", {})
        # 문자열/숫자 혼용 방어: 값 리스트를 float로 정규화
        norm_grid = {k: [float(v) for v in vals] for k, vals in grid.items() if vals}
        out = optimize(
            {symbol: closes},
            payload.get("params", {}),
            norm_grid,
            objective=payload.get("objective", "return"),
            top=int(payload.get("top", 15)),
        )
        out["symbol"] = symbol
        return out


def serve(port: int = 8000, host: str = "127.0.0.1") -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"AIbot 대시보드 실행 중 → http://{host}:{port}  (Ctrl+C 종료)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
        server.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="AIbot 웹 대시보드")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    serve(port=args.port, host=args.host)


INDEX_HTML = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AIbot 자동매매 대시보드</title>
<style>
  :root{--bg:#f6f7f9;--panel:#fff;--text:#1a1d23;--muted:#6b7280;--border:#e5e7eb;
    --accent:#2563eb;--pos:#16a34a;--neg:#dc2626;}
  @media (prefers-color-scheme:dark){:root{--bg:#0f1115;--panel:#171a21;--text:#e6e8eb;
    --muted:#9aa1ab;--border:#262b34;--accent:#3b82f6;--pos:#22c55e;--neg:#ef4444;}}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;line-height:1.5}
  .wrap{max-width:1000px;margin:0 auto;padding:24px 18px 60px}
  h1{font-size:20px;margin:0 0 2px}
  .sub{color:var(--muted);font-size:13px;margin:0 0 20px}
  .grid{display:grid;grid-template-columns:320px 1fr;gap:20px}
  @media(max-width:820px){.grid{grid-template-columns:1fr}}
  .panel{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px}
  .panel h2{font-size:13px;margin:0 0 14px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.03em}
  label{display:block;font-size:12px;color:var(--muted);margin:10px 0 4px}
  input,select{width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:8px;
    background:var(--bg);color:var(--text);font-size:13px}
  .row{display:flex;gap:10px}.row>div{flex:1}
  .check{display:flex;align-items:center;gap:8px;margin-top:12px}
  .check input{width:auto}
  button{margin-top:16px;width:100%;padding:11px;border:0;border-radius:9px;background:var(--accent);
    color:#fff;font-size:14px;font-weight:600;cursor:pointer}
  button:disabled{opacity:.6;cursor:progress}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin-bottom:16px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
  .card .l{font-size:11px;color:var(--muted)}
  .card .v{font-size:18px;font-weight:650;font-variant-numeric:tabular-nums}
  .pos{color:var(--pos)}.neg{color:var(--neg)}
  table{width:100%;border-collapse:collapse;font-size:12.5px}
  th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--border)}
  th{color:var(--muted);font-size:11px}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  td.reason{color:var(--muted);font-size:11px}
  .pill{display:inline-block;padding:2px 7px;border-radius:999px;font-size:10.5px;font-weight:600}
  .pill.buy{background:rgba(22,163,74,.15);color:var(--pos)}
  .pill.sell{background:rgba(220,38,38,.15);color:var(--neg)}
  .muted{color:var(--muted);font-size:12px}
  .tablewrap{max-height:340px;overflow:auto}
  .err{color:var(--neg);font-size:13px;margin-top:10px}
  .warn{font-size:11.5px;color:var(--muted);margin-top:18px;border-top:1px solid var(--border);padding-top:12px}
  .hidden{display:none}
</style>
</head>
<body>
<div class="wrap">
  <h1>AIbot 자동매매 대시보드</h1>
  <p class="sub">모의(PaperBroker) 백테스트 · 실제 투자 결과가 아닙니다</p>
  <div class="grid">
    <!-- 설정 패널 -->
    <div class="panel">
      <h2>전략 설정</h2>
      <label>데이터 소스</label>
      <select id="source">
        <option value="sample">샘플 (005930 일봉)</option>
        <option value="csv">CSV 업로드</option>
        <option value="randomwalk">랜덤워크(데모)</option>
      </select>

      <div id="csvBox" class="hidden">
        <label>CSV 파일 (날짜/종가 컬럼 자동 인식)</label>
        <input type="file" id="csvFile" accept=".csv,text/csv"/>
      </div>

      <label>종목코드</label>
      <input id="symbol" value="005930"/>

      <label>진입 방식</label>
      <select id="entry">
        <option value="target">지정가 (목표가 이하 매수)</option>
        <option value="indicator">지표 (RSI/이평 돌파)</option>
      </select>

      <div id="targetBox">
        <label>목표 매수가</label>
        <input id="target" type="number" value="70000"/>
      </div>

      <div class="row">
        <div><label>익절 %</label><input id="tp" type="number" step="0.1" value="3"/></div>
        <div><label>손절 %</label><input id="sl" type="number" step="0.1" value="2"/></div>
      </div>
      <div class="row">
        <div><label>수량</label><input id="qty" type="number" value="100"/></div>
        <div><label>트레일링스톱 %</label><input id="ts" type="number" step="0.1" value="0"/></div>
      </div>
      <label>시작 현금</label>
      <input id="cash" type="number" value="10000000"/>

      <div class="check"><input type="checkbox" id="deadcross"/><label for="deadcross" style="margin:0">데드크로스 매도 사용</label></div>

      <button id="run">백테스트 실행 ▶</button>

      <div class="row" style="margin-top:10px">
        <div><button id="live" style="background:#059669;margin-top:0">실시간 시작 ▶</button></div>
        <div><button id="livestop" style="background:#4b5563;margin-top:0" disabled>정지 ■</button></div>
      </div>

      <h2 style="margin-top:22px">파라미터 자동 최적화</h2>
      <label>익절% 후보 (콤마)</label><input id="tpGrid" value="2,3,4,5"/>
      <label>손절% 후보 (콤마)</label><input id="slGrid" value="1,2,3"/>
      <label>트레일링% 후보 (콤마, 0=미사용)</label><input id="tsGrid" value="0,3,5"/>
      <label>최적화 목표</label>
      <select id="objective">
        <option value="return">총 수익률</option>
        <option value="return_dd">위험조정수익(수익률/낙폭)</option>
        <option value="winrate">승률</option>
      </select>
      <button id="opt" style="background:#7c3aed">최적화 실행 ⚙</button>
      <div id="err" class="err"></div>
    </div>

    <!-- 결과 패널 -->
    <div>
      <div id="livePanel" class="panel hidden" style="margin-bottom:16px">
        <h2><span id="liveDot" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--pos);margin-right:6px"></span>실시간 모니터 <span id="liveState" class="muted"></span></h2>
        <div style="display:flex;align-items:baseline;gap:14px;margin-bottom:8px">
          <div id="liveEquity" style="font-size:24px;font-weight:700;font-variant-numeric:tabular-nums">-</div>
          <div id="liveRet" style="font-size:16px;font-weight:600">-</div>
          <div id="liveTick" class="muted"></div>
        </div>
        <div id="liveChart" style="color:var(--muted)"></div>
        <div id="livePos" class="muted" style="margin-top:8px"></div>
        <div class="tablewrap" style="max-height:180px;margin-top:8px"><table id="liveTrades"></table></div>
      </div>
      <div id="cards" class="cards"></div>
      <div class="panel" style="margin-bottom:16px">
        <h2>평가금액 곡선</h2>
        <div id="chart" style="color:var(--muted)"><p class="muted">실행하면 결과가 표시됩니다.</p></div>
      </div>
      <div id="optPanel" class="panel hidden" style="margin-bottom:16px">
        <h2>최적화 결과 (행 클릭 시 해당 조합 적용)</h2>
        <div class="tablewrap"><table id="optTable"></table></div>
      </div>
      <div class="panel">
        <h2>매매 내역</h2>
        <div class="tablewrap"><table id="trades"><tbody><tr><td class="muted">아직 없음</td></tr></tbody></table></div>
      </div>
      <p class="warn">⚠️ 모의 백테스트입니다. 전략 로직 검증용이며 실제 수익을 보장하지 않습니다.
      실계좌 연결 전 반드시 증권사 모의투자로 재검증하세요.</p>
    </div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
const fmt = n => Number(n).toLocaleString('ko-KR');

$('source').onchange = () => $('csvBox').classList.toggle('hidden', $('source').value !== 'csv');
$('entry').onchange = () => $('targetBox').classList.toggle('hidden', $('entry').value !== 'target');

function readFile(file){
  return new Promise((res,rej)=>{
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.onerror = rej;
    r.readAsText(file);
  });
}

function drawChartInto(elId, values){
  const el=$(elId);
  if(!values || values.length < 2){ el.innerHTML = '<p class="muted">데이터 부족</p>'; return; }
  const W=820,H=240,pad=8;
  const lo=Math.min(...values), hi=Math.max(...values), span=(hi-lo)||1;
  const x=i=>pad+i*(W-2*pad)/(values.length-1);
  const y=v=>pad+(1-(v-lo)/span)*(H-2*pad);
  const pts=values.map((v,i)=>[x(i),y(v)]);
  const line=pts.map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ');
  const base=values[0], up=values[values.length-1]>=base;
  const col=up?'#16a34a':'#dc2626';
  const area='M '+pts[0][0].toFixed(1)+','+(H-pad)+' '+pts.map(p=>'L '+p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ')+' L '+pts[pts.length-1][0].toFixed(1)+','+(H-pad)+' Z';
  el.innerHTML =
    '<svg viewBox="0 0 '+W+' '+H+'" width="100%" preserveAspectRatio="none">'+
    '<line x1="'+pad+'" y1="'+y(base).toFixed(1)+'" x2="'+(W-pad)+'" y2="'+y(base).toFixed(1)+'" stroke="currentColor" stroke-opacity="0.25" stroke-dasharray="4 4"/>'+
    '<path d="'+area+'" fill="'+col+'" fill-opacity="0.16"/>'+
    '<polyline points="'+line+'" fill="none" stroke="'+col+'" stroke-width="2" stroke-linejoin="round"/></svg>';
}
function drawChart(values){ drawChartInto('chart', values); }

function renderCards(s){
  const t = s.total_return_pct;
  const tone = t>=0?'pos':'neg';
  const items = [
    ['총 수익률',(t>=0?'+':'')+t+'%',tone],
    ['최종 평가금액',fmt(s.end_equity),''],
    ['승률',s.win_rate_pct+'%',''],
    ['최대 낙폭','-'+s.max_drawdown_pct+'%',s.max_drawdown_pct?'neg':''],
    ['매매 사이클',s.num_round_trips+'회',''],
    ['총 체결',s.num_trades+'건',''],
  ];
  $('cards').innerHTML = items.map(([l,v,c])=>
    '<div class="card"><div class="l">'+l+'</div><div class="v '+c+'">'+v+'</div></div>').join('');
}

function renderTrades(trades){
  if(!trades.length){ $('trades').innerHTML='<tbody><tr><td class="muted">매매 없음</td></tr></tbody>'; return; }
  const head='<thead><tr><th>구분</th><th>종목</th><th>수량</th><th>체결가</th><th>사유</th></tr></thead>';
  const rows=trades.map(t=>{
    const buy=t.action.indexOf('BUY')===0;
    return '<tr><td><span class="pill '+(buy?'buy':'sell')+'">'+t.action+'</span></td>'+
      '<td>'+t.symbol+'</td><td class="num">'+t.quantity+'</td><td class="num">'+fmt(t.price)+'</td>'+
      '<td class="reason">'+t.reason+'</td></tr>';
  }).join('');
  $('trades').innerHTML=head+'<tbody>'+rows+'</tbody>';
}

function buildParams(){
  const params={
    tp:parseFloat($('tp').value), sl:parseFloat($('sl').value),
    qty:parseInt($('qty').value), cash:parseFloat($('cash').value),
    trailing_stop_pct:parseFloat($('ts').value),
    use_sma_cross_exit:$('deadcross').checked,
  };
  if($('entry').value==='target'){ params.target=parseFloat($('target').value); params.buy_logic='OR'; }
  return params;
}

async function buildBody(){
  const source=$('source').value;
  const body={source, symbol:$('symbol').value};
  if(source==='csv'){
    const f=$('csvFile').files[0];
    if(!f) throw new Error('CSV 파일을 선택하세요.');
    body.csv_text=await readFile(f);
  }
  return body;
}

function parseGrid(s){ return s.split(',').map(x=>parseFloat(x)).filter(x=>!isNaN(x)); }

$('run').onclick = async () => {
  $('err').textContent=''; $('run').disabled=true; $('run').textContent='실행 중…';
  try{
    const body=await buildBody(); body.params=buildParams();
    const res=await fetch('/api/backtest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'실행 실패');
    renderCards(data.stats); drawChart(data.equity_curve); renderTrades(data.trades);
  }catch(e){ $('err').textContent='오류: '+e.message; }
  finally{ $('run').disabled=false; $('run').textContent='백테스트 실행 ▶'; }
};

function renderOpt(out){
  $('optPanel').classList.remove('hidden');
  const head='<thead><tr><th>#</th><th>익절%</th><th>손절%</th><th>트레일%</th><th>수익률</th><th>승률</th><th>MDD</th><th>체결</th></tr></thead>';
  const rows=out.results.map((r,i)=>{
    const p=r.params, s=r.stats, tone=s.total_return_pct>=0?'pos':'neg';
    return '<tr style="cursor:pointer" data-tp="'+p.tp+'" data-sl="'+p.sl+'" data-ts="'+p.trailing_stop_pct+'">'+
      '<td>'+(i+1)+'</td><td class="num">'+p.tp+'</td><td class="num">'+p.sl+'</td>'+
      '<td class="num">'+p.trailing_stop_pct+'</td><td class="num '+tone+'">'+(s.total_return_pct>=0?'+':'')+s.total_return_pct+'%</td>'+
      '<td class="num">'+s.win_rate_pct+'%</td><td class="num">-'+s.max_drawdown_pct+'%</td><td class="num">'+s.num_trades+'</td></tr>';
  }).join('');
  const tbl=$('optTable'); tbl.innerHTML=head+'<tbody>'+rows+'</tbody>';
  tbl.querySelectorAll('tbody tr').forEach(tr=>{
    tr.onclick=()=>{ $('tp').value=tr.dataset.tp; $('sl').value=tr.dataset.sl; $('ts').value=tr.dataset.ts; $('run').click(); };
  });
}

let livePoll=null;
function renderLive(s){
  $('livePanel').classList.remove('hidden');
  $('liveEquity').textContent = fmt(Math.round(s.equity));
  const r=s.return_pct;
  $('liveRet').textContent=(r>=0?'+':'')+r+'%';
  $('liveRet').className=r>=0?'pos':'neg';
  $('liveTick').textContent='틱 '+(s.tick+1);
  $('liveDot').style.background=s.running?'var(--pos)':'var(--muted)';
  $('liveState').textContent=s.running?'실행 중':'정지됨';
  drawChartInto('liveChart', s.equity_curve);
  $('livePos').textContent = s.positions.length
    ? '보유: '+s.positions.map(p=>p.symbol+' '+p.quantity+'주('+(p.pnl_pct>=0?'+':'')+p.pnl_pct+'%)').join('  ')
    : '보유 없음';
  const rows=s.trades.map(t=>{
    const buy=t.action.indexOf('BUY')===0;
    return '<tr><td class="muted">틱'+t.tick+'</td><td><span class="pill '+(buy?'buy':'sell')+'">'+t.action+'</span></td>'+
      '<td>'+t.symbol+'</td><td class="num">'+t.quantity+'</td><td class="num">'+fmt(t.price)+'</td><td class="reason">'+t.reason+'</td></tr>';
  }).join('');
  $('liveTrades').innerHTML='<tbody>'+(rows||'<tr><td class="muted">체결 대기 중…</td></tr>')+'</tbody>';
}
async function pollLive(){
  try{
    const res=await fetch('/api/live/state');
    const s=await res.json();
    if(!s.ok) return;
    renderLive(s);
    if(!s.running){ stopPolling(); }
  }catch(e){ stopPolling(); }
}
function stopPolling(){
  if(livePoll){ clearInterval(livePoll); livePoll=null; }
  $('live').disabled=false; $('live').textContent='실시간 시작 ▶';
  $('livestop').disabled=true;
}
$('live').onclick = async () => {
  $('err').textContent='';
  try{
    const body=await buildBody(); body.params=buildParams();
    body.interval=0.4; body.ticks=300;
    if($('entry').value==='target') body.start_price=parseFloat($('target').value);
    const res=await fetch('/api/live/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await res.json();
    if(!d.ok) throw new Error(d.error||'시작 실패');
    $('live').disabled=true; $('live').textContent='실행 중…'; $('livestop').disabled=false;
    if(livePoll) clearInterval(livePoll);
    livePoll=setInterval(pollLive, 500); pollLive();
  }catch(e){ $('err').textContent='오류: '+e.message; }
};
$('livestop').onclick = async () => {
  await fetch('/api/live/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
};

$('opt').onclick = async () => {
  $('err').textContent=''; $('opt').disabled=true; $('opt').textContent='탐색 중…';
  try{
    const body=await buildBody();
    body.params=buildParams();
    // 그리드로 스윕하므로 개별 tp/sl/ts는 base에서 제거
    delete body.params.tp; delete body.params.sl; delete body.params.trailing_stop_pct;
    body.grid={
      tp:parseGrid($('tpGrid').value),
      sl:parseGrid($('slGrid').value),
      trailing_stop_pct:parseGrid($('tsGrid').value),
    };
    body.objective=$('objective').value;
    const res=await fetch('/api/optimize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'최적화 실패');
    renderOpt(data);
  }catch(e){ $('err').textContent='오류: '+e.message; }
  finally{ $('opt').disabled=false; $('opt').textContent='최적화 실행 ⚙'; }
};
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
