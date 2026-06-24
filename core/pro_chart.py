from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


CHART_HTML = """
<div class="shell">
  <div class="toolbar">
    <div class="symbol"></div><div class="legend">Chargement…</div>
    <button data-action="fit">Ajuster</button>
    <button data-action="support">Support</button>
    <button data-action="resistance">Résistance</button>
    <button data-action="trend">Tendance</button>
    <button data-action="clear">Effacer</button>
    <button data-action="full">Plein écran</button>
  </div>
  <div class="hint">Clique deux points sur le graphique</div>
  <div class="chart"></div>
</div>
"""

CHART_CSS = """
*{box-sizing:border-box}.shell{height:100%;min-height:420px;border-radius:18px;overflow:hidden;border:1px solid rgba(96,165,250,.20);position:relative}
.toolbar{height:48px;display:flex;align-items:center;gap:8px;padding:7px 10px;border-bottom:1px solid rgba(96,165,250,.16)}
.symbol{font-size:14px;font-weight:900;margin-right:auto}.legend{font-size:12px;opacity:.75}
button{border:1px solid rgba(96,165,250,.24);background:transparent;color:inherit;border-radius:9px;padding:7px 10px;cursor:pointer;font-weight:700}
button:hover,button.active{background:#2563EB;color:#fff}.chart{height:calc(100% - 48px)}
.hint{position:absolute;z-index:4;right:18px;top:60px;padding:6px 9px;border-radius:8px;background:rgba(15,39,66,.90);color:white;font-size:11px;display:none}
@media(max-width:700px){button[data-action="support"],button[data-action="resistance"],button[data-action="clear"]{display:none}.legend{display:none}}
"""

CHART_JS = r"""
export default function(component) {
  const { data, parentElement } = component;
  let disposed = false;
  let observer = null;
  let chart = null;

  async function loadLibrary() {
    if (window.LightweightCharts) return;
    await new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-skyline-lwc]');
      if (existing) { existing.addEventListener('load', resolve, {once:true}); existing.addEventListener('error', reject, {once:true}); return; }
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/lightweight-charts@4.2.2/dist/lightweight-charts.standalone.production.js';
      script.dataset.skylineLwc = '1';
      script.onload = resolve; script.onerror = reject; document.head.appendChild(script);
    });
  }

  async function mount() {
    try { await loadLibrary(); } catch (error) {
      parentElement.querySelector('.chart').innerHTML = '<div style="padding:24px;color:#DC2626">Le graphique professionnel ne peut pas charger son CDN. Active le mode compatibilité Plotly.</div>';
      return;
    }
    if (disposed) return;
    const root = parentElement.querySelector('.shell');
    const chartNode = parentElement.querySelector('.chart');
    const toolbar = parentElement.querySelector('.toolbar');
    const legend = parentElement.querySelector('.legend');
    const hint = parentElement.querySelector('.hint');
    const symbol = parentElement.querySelector('.symbol');
    root.style.background = data.theme.bg; root.style.color = data.theme.text; toolbar.style.background = data.theme.panel;
    symbol.textContent = data.ticker;
    chartNode.innerHTML = '';
    chart = LightweightCharts.createChart(chartNode, {
      layout:{background:{type:'solid',color:data.theme.bg},textColor:data.theme.text},
      grid:{vertLines:{color:data.theme.grid},horzLines:{color:data.theme.grid}},
      crosshair:{mode:LightweightCharts.CrosshairMode.Normal},rightPriceScale:{borderColor:data.theme.grid},
      timeScale:{borderColor:data.theme.grid,timeVisible:true,secondsVisible:false},localization:{priceFormatter:p=>p.toFixed(2)}
    });
    const series=chart.addCandlestickSeries({upColor:'#10B981',downColor:'#EF4444',borderVisible:false,wickUpColor:'#10B981',wickDownColor:'#EF4444'});
    series.setData(data.candles);
    const volume=chart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'vol'});
    volume.priceScale().applyOptions({scaleMargins:{top:.82,bottom:0}}); volume.setData(data.volumes);
    if(data.markers?.length) series.setMarkers(data.markers);
    (data.priceLines||[]).forEach(l=>series.createPriceLine({price:Number(l.price),color:l.color||'#F59E0B',lineWidth:2,lineStyle:2,axisLabelVisible:true,title:l.title||''}));
    let drawings=[]; let trendMode=false; let trendPoints=[];
    const addPriceLine=(title,color,offset)=>{const last=data.candles.at(-1).close;const line=series.createPriceLine({price:last*(1+offset),color,lineWidth:2,lineStyle:2,axisLabelVisible:true,title});drawings.push(['price',line]);};
    toolbar.querySelector('[data-action="support"]').onclick=()=>addPriceLine('Support','#0EA5E9',-.02);
    toolbar.querySelector('[data-action="resistance"]').onclick=()=>addPriceLine('Résistance','#F59E0B',.02);
    toolbar.querySelector('[data-action="fit"]').onclick=()=>chart.timeScale().fitContent();
    toolbar.querySelector('[data-action="full"]').onclick=()=>{if(!document.fullscreenElement)root.requestFullscreen();else document.exitFullscreen();};
    toolbar.querySelector('[data-action="trend"]').onclick=(event)=>{trendMode=!trendMode;trendPoints=[];event.currentTarget.classList.toggle('active',trendMode);hint.style.display=trendMode?'block':'none';};
    chart.subscribeClick(param=>{if(!trendMode||!param.point||!param.time)return;const price=series.coordinateToPrice(param.point.y);trendPoints.push({time:param.time,value:price});if(trendPoints.length===2){const line=chart.addLineSeries({color:'#8B5CF6',lineWidth:2,priceLineVisible:false,lastValueVisible:false});line.setData(trendPoints);drawings.push(['series',line]);trendMode=false;toolbar.querySelector('[data-action="trend"]').classList.remove('active');hint.style.display='none';}});
    toolbar.querySelector('[data-action="clear"]').onclick=()=>{drawings.forEach(d=>{try{d[0]==='price'?series.removePriceLine(d[1]):chart.removeSeries(d[1]);}catch(e){}});drawings=[];};
    chart.subscribeCrosshairMove(param=>{if(!param.time)return;const point=param.seriesData.get(series);if(point)legend.textContent=`O ${point.open.toFixed(2)}  H ${point.high.toFixed(2)}  L ${point.low.toFixed(2)}  C ${point.close.toFixed(2)}`;});
    observer=new ResizeObserver(entries=>{for(const entry of entries)chart.applyOptions({width:entry.contentRect.width,height:entry.contentRect.height});}); observer.observe(chartNode);
    chart.timeScale().fitContent();
  }
  mount();
  return () => { disposed=true; if(observer)observer.disconnect(); if(chart)chart.remove(); };
}
"""

def _iso_time(index_value: Any) -> str:
    stamp = pd.Timestamp(index_value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("America/Toronto").tz_localize(None)
    return stamp.strftime("%Y-%m-%d")


def build_event_markers(news: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for article in (news or [])[:12]:
        raw = article.get("published") or article.get("providerPublishTime") or article.get("Date")
        if not raw:
            continue
        try:
            stamp = pd.to_datetime(raw, utc=True).tz_convert("America/Toronto")
        except Exception:
            continue
        markers.append({"time":stamp.strftime("%Y-%m-%d"),"position":"aboveBar","color":"#0EA5E9","shape":"circle","text":"N"})
    return markers


def render_professional_chart(
    history: pd.DataFrame,
    ticker: str,
    markers: list[dict[str, Any]] | None = None,
    price_lines: list[dict[str, Any]] | None = None,
    height: int = 720,
    dark: bool = False,
    key: str | None = None,
) -> None:
    if history is None or history.empty:
        st.info("Historique indisponible pour le graphique professionnel.")
        return
    required = {"Open", "High", "Low", "Close"}
    if not required.issubset(history.columns):
        st.warning("Les colonnes OHLC nécessaires sont absentes.")
        return
    clean = history.copy().dropna(subset=list(required))
    candles=[{"time":_iso_time(i),"open":round(float(r["Open"]),4),"high":round(float(r["High"]),4),"low":round(float(r["Low"]),4),"close":round(float(r["Close"]),4)} for i,r in clean.iterrows()]
    volumes=[{"time":_iso_time(i),"value":float(r.get("Volume",0) or 0),"color":"rgba(16,185,129,.48)" if float(r["Close"])>=float(r["Open"]) else "rgba(239,68,68,.48)"} for i,r in clean.iterrows()]
    theme={"text":"#EAF6FF" if dark else "#102D49","grid":"rgba(148,184,210,.10)" if dark else "rgba(74,125,167,.12)","bg":"#0B1F30" if dark else "#F8FCFF","panel":"#102D44" if dark else "#FFFFFF"}
    professional_chart_component = st.components.v2.component(
        "skyline_professional_chart",
        html=CHART_HTML,
        css=CHART_CSS,
        js=CHART_JS,
    )
    professional_chart_component(
        data={"ticker":ticker,"candles":candles,"volumes":volumes,"markers":markers or [],"priceLines":price_lines or [],"theme":theme},
        key=key,
        width="stretch",
        height=height,
    )
