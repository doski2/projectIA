"""Sección interactiva del informe: velocidad, CTE, volante y pedales por vuelta con zoom.

`zoom_html(ticks, cat)` devuelve un bloque HTML autónomo (canvas + JavaScript propio, sin librerías ni red)
para pegarlo en el informe. Todos los paneles comparten el eje de distancia:

- rueda del ratón: zoom en la distancia bajo el cursor; arrastrar: desplazar; doble clic: ver todo;
- lista «ir a la curva»: encuadra una curva del catálogo (C1-C14);
- el eje vertical se ajusta solo a lo que se ve (se puede apagar);
- panel «Δ velocidad»: cada vuelta menos una vuelta de referencia a la misma distancia, que es donde se ven
  las diferencias pequeñas entre vueltas que en la gráfica de velocidad quedan tapadas;
- las vueltas se encienden y apagan con su casilla; al pasar el ratón salen los valores de cada vuelta.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# (clave del panel, título, altura en px, campo del tick)
_PANELES = (
    ("v", "Velocidad (km/h)", 280),
    ("dv", "Δ velocidad frente a la vuelta de referencia (km/h)", 150),
    ("cte", "CTE firmado (m)", 170),
    ("vol", "Volante", 150),
    ("ped", "Gas − freno", 150),
)


def datos_zoom(ticks: List[dict], cat: Any = None, paso_m: float = 1.5) -> Optional[Dict[str, Any]]:
    """Series por vuelta reducidas a un punto cada `paso_m` metros (la distancia siempre crece). None si no hay vueltas."""
    con_cte = bool(ticks) and "signed_cte" in ticks[0]
    vueltas: Dict[int, Dict[str, list]] = {}
    ultimo: Dict[int, float] = {}
    for t in ticks:
        try:
            n = int(t["lap"])
            d = float(t["lap_distance"])
            v = float(t["speed_kmh"])
        except (KeyError, TypeError, ValueError):
            continue
        if d != d or v != v:  # NaN
            continue
        if n in ultimo and d < ultimo[n] + paso_m:
            continue
        ultimo[n] = d
        s = vueltas.setdefault(n, {"d": [], "v": [], "cte": [], "vol": [], "ped": []})
        s["d"].append(round(d, 1))
        s["v"].append(round(v, 2))
        if con_cte:
            s["cte"].append(round(float(t.get("signed_cte") or 0.0), 3))
            s["vol"].append(round(float(t.get("steering") or 0.0), 3))
            s["ped"].append(round(float(t.get("throttle") or 0.0) - float(t.get("brake") or 0.0), 3))
    vueltas = {n: s for n, s in vueltas.items() if len(s["d"]) >= 20}
    if not vueltas:
        return None
    claves = ["v"] + (["dv"] if len(vueltas) >= 2 else []) + (["cte", "vol", "ped"] if con_cte else [])
    largo = max(max(s["d"]) for s in vueltas.values())
    curvas: List[dict] = []
    if cat is not None:
        largo = max(largo, float(getattr(cat, "longitud_m", 0.0) or 0.0))
        for c in cat.curvas:
            curvas.append({"id": int(c.id), "a": float(c.s_ini), "b": float(c.s_fin), "apice": float(c.s_apice),
                           "izq": c.sentido == "izq"})
    return {
        "paneles": [{"k": k, "t": t, "h": h} for k, t, h in _PANELES if k in claves],
        "vueltas": [{"n": n, **vueltas[n]} for n in sorted(vueltas)],
        "curvas": curvas,
        "largo": round(largo, 1),
    }


def zoom_html(ticks: List[dict], cat: Any = None) -> str:
    datos = datos_zoom(ticks, cat)
    if datos is None:
        return ""
    # `</` dentro de un <script> cerraría la etiqueta antes de tiempo
    blob = json.dumps(datos, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    return _PLANTILLA.replace("__DATOS__", blob)


_PLANTILLA = r"""
<h2>Velocidad, CTE y pedales por vuelta (con zoom)</h2>
<style>
#zoomroot .barra{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;margin:6px 0;font-size:13px}
#zoomroot button,#zoomroot select{font:inherit;padding:2px 8px}
#zoomroot .lap{cursor:pointer;user-select:none;white-space:nowrap}
#zoomroot .lap i{display:inline-block;width:12px;height:3px;margin-right:4px;vertical-align:middle}
#zoomroot .cab{font-size:12px;margin-top:8px;min-height:16px;white-space:nowrap;overflow:hidden}
#zoomroot canvas{display:block;width:100%;border:1px solid #ccc;background:#fff;cursor:crosshair;touch-action:none}
#zoomroot .ayuda{font-size:12px;color:#555}
</style>
<div id="zoomroot">
  <div class="barra" id="zbarra"></div>
  <div class="ayuda">Rueda: zoom en el cursor · arrastrar: mover · doble clic: ver todo · las zonas naranja son curvas a la izquierda y las azules a la derecha.</div>
  <div id="zpaneles"></div>
</div>
<script>
(function(){
var D=__DATOS__;
var COL=['#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd','#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf'];
var laps=D.vueltas, panels=D.paneles, N=D.largo;
var visible=laps.map(function(L,i){return !(i===0&&laps.length>2);}); // la 1.ª lleva la salida parada
var x0=0,x1=N,cur=null,autoY=true,ref=Math.min(laps.length-1,laps.length>1?1:0);
function esc(s){return String(s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
function lower(a,x){var lo=0,hi=a.length;while(lo<hi){var m=(lo+hi)>>1;if(a[m]<x)lo=m+1;else hi=m;}return lo;}
function interp(L,arr,x){var i=lower(L.d,x);if(i<=0||i>=L.d.length)return null;
  var d0=L.d[i-1],d1=L.d[i];if(d1-d0>6)return null;return arr[i-1]+(arr[i]-arr[i-1])*(x-d0)/((d1-d0)||1);}
function calcDv(){laps.forEach(function(L){var R=laps[ref];L.dv=L.d.map(function(d,i){
  var r=interp(R,R.v,d);return r===null?NaN:Math.round((L.v[i]-r)*100)/100;});});}
function curvaEn(x){for(var i=0;i<D.curvas.length;i++){var c=D.curvas[i];
  if(c.a<=c.b?(x>=c.a&&x<=c.b):(x>=c.a||x<=c.b))return c;}return null;}
function nice(lo,hi,n){var r=hi-lo||1,p=Math.pow(10,Math.floor(Math.log(r/n)/Math.LN10)),e=r/n/p;
  var s=(e<1.5?1:e<3?2:e<7?5:10)*p,out=[];for(var v=Math.ceil(lo/s)*s;v<=hi+1e-9;v+=s)out.push(Math.round(v/s)*s);return out;}
// barra de controles
var barra=document.getElementById('zbarra'),cont=document.getElementById('zpaneles');
var h='<button id="zmas">+</button><button id="zmenos">−</button><button id="ztodo">Todo</button>';
if(D.curvas.length){h+='<select id="zcurva"><option value="">ir a la curva…</option>';
  D.curvas.forEach(function(c){h+='<option value="'+c.id+'">C'+c.id+' ('+Math.round(c.apice)+' m)</option>';});h+='</select>';}
h+='<label><input type="checkbox" id="zauto" checked> eje vertical automático</label>';
if(panels.some(function(p){return p.k==='dv';})){h+='<label>referencia del Δ: <select id="zref">';
  laps.forEach(function(L,i){h+='<option value="'+i+'"'+(i===ref?' selected':'')+'>vuelta '+L.n+'</option>';});h+='</select></label>';}
laps.forEach(function(L,i){h+='<span class="lap" data-i="'+i+'"><input type="checkbox"'+(visible[i]?' checked':'')+'> <i style="background:'+COL[i%COL.length]+'"></i>vuelta '+L.n+'</span>';});
barra.innerHTML=h;
// paneles
panels.forEach(function(p){var d=document.createElement('div');
  d.innerHTML='<div class="cab" id="cab_'+p.k+'"><b>'+esc(p.t)+'</b></div><canvas id="cv_'+p.k+'" style="height:'+p.h+'px"></canvas>';
  cont.appendChild(d);p.cv=d.querySelector('canvas');p.cab=d.querySelector('.cab');p.ctx=p.cv.getContext('2d');});
var ML=52,MR=8,MT=6,MB=20;
function rangoY(p){var lo=Infinity,hi=-Infinity,key=p.k;
  laps.forEach(function(L,i){if(!visible[i])return;var a=L[key],j=Math.max(0,lower(L.d,x0)-1),e=Math.min(L.d.length,lower(L.d,x1)+1);
    for(var k=j;k<e;k++){var v=a[k];if(v===v){if(v<lo)lo=v;if(v>hi)hi=v;}}});
  if(!(lo<=hi)){lo=0;hi=1;}if(key==='dv'){lo=Math.min(lo,0);hi=Math.max(hi,0);}
  if(key==='ped'){lo=Math.min(lo,-0.05);hi=Math.max(hi,0.05);}
  var m=(hi-lo)*0.06||0.5;return [lo-m,hi+m];}
function dibuja(p){var cv=p.cv,dpr=window.devicePixelRatio||1,W=cv.clientWidth,H=p.h;
  if(cv.width!==Math.round(W*dpr)||cv.height!==Math.round(H*dpr)){cv.width=Math.round(W*dpr);cv.height=Math.round(H*dpr);}
  var c=p.ctx;c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,W,H);
  var r=autoY?rangoY(p):(p.fijo||rangoY(p));if(autoY)p.fijo=r;var y0=r[0],y1=r[1];
  function X(x){return ML+(x-x0)/(x1-x0)*(W-ML-MR);}function Y(y){return MT+(1-(y-y0)/(y1-y0))*(H-MT-MB);}
  D.curvas.forEach(function(k){c.fillStyle=k.izq?'rgba(255,127,14,.10)':'rgba(31,119,180,.10)';
    var seg=k.a<=k.b?[[k.a,k.b]]:[[k.a,N],[0,k.b]];seg.forEach(function(s){var a=Math.max(s[0],x0),b=Math.min(s[1],x1);
      if(b>a)c.fillRect(X(a),MT,X(b)-X(a),H-MT-MB);});
    if(k.apice>=x0&&k.apice<=x1&&p.k==='v'){c.fillStyle='#000';c.font='bold 11px system-ui';c.textAlign='center';c.fillText('C'+k.id,X(k.apice),MT+11);}});
  c.font='11px system-ui';c.fillStyle='#444';c.strokeStyle='#e4e4e4';c.lineWidth=1;c.textAlign='right';
  nice(y0,y1,5).forEach(function(v){var y=Math.round(Y(v))+.5;c.beginPath();c.moveTo(ML,y);c.lineTo(W-MR,y);c.stroke();
    c.fillText((Math.abs(v)<1e-9?0:+v.toPrecision(4)).toString(),ML-4,y+4);});
  c.textAlign='center';nice(x0,x1,10).forEach(function(v){var x=Math.round(X(v))+.5;c.beginPath();c.moveTo(x,MT);c.lineTo(x,H-MB);c.stroke();
    c.fillText(Math.round(v)+'',x,H-6);});
  if(p.k==='dv'||p.k==='cte'||p.k==='vol'||p.k==='ped'){var yz=Math.round(Y(0))+.5;if(yz>MT&&yz<H-MB){c.strokeStyle='#999';c.beginPath();c.moveTo(ML,yz);c.lineTo(W-MR,yz);c.stroke();}}
  c.save();c.beginPath();c.rect(ML,MT,W-ML-MR,H-MT-MB);c.clip();c.lineWidth=1.3;c.lineJoin='round';
  laps.forEach(function(L,i){if(!visible[i])return;var a=L[p.k];c.strokeStyle=COL[i%COL.length];c.beginPath();
    var j=Math.max(0,lower(L.d,x0)-1),e=Math.min(L.d.length,lower(L.d,x1)+1),pen=false;
    for(var k=j;k<e;k++){var v=a[k];if(v!==v||(k>j&&L.d[k]-L.d[k-1]>20)){pen=false;continue;}
      var px=X(L.d[k]),py=Y(v);if(pen)c.lineTo(px,py);else{c.moveTo(px,py);pen=true;}}
    c.stroke();});
  c.restore();
  if(cur!==null&&cur>=x0&&cur<=x1){c.strokeStyle='#333';c.lineWidth=1;c.setLineDash([4,3]);var xc=Math.round(X(cur))+.5;
    c.beginPath();c.moveTo(xc,MT);c.lineTo(xc,H-MB);c.stroke();c.setLineDash([]);}
  p.X=X;p.inv=function(px){return x0+(px-ML)/(W-ML-MR)*(x1-x0);};}
function cabeceras(){var k=cur===null?null:curvaEn(cur);
  panels.forEach(function(p){var s='<b>'+esc(p.t)+'</b>';
    if(cur!==null){s+=' · '+Math.round(cur)+' m'+(k?' · C'+k.id:'');
      laps.forEach(function(L,i){if(!visible[i])return;var v=interp(L,L[p.k],cur);
        if(v!==null)s+=' · <span style="color:'+COL[i%COL.length]+'">V'+L.n+' '+(+v.toFixed(p.k==='cte'||p.k==='vol'||p.k==='ped'?3:1))+'</span>';});}
    p.cab.innerHTML=s;});}
function todo(){panels.forEach(dibuja);cabeceras();}
function limita(){var span=x1-x0;if(span>N){x0=0;x1=N;return;}if(span<20){var m=(x0+x1)/2;x0=m-10;x1=m+10;}
  if(x0<0){x1-=x0;x0=0;}if(x1>N){x0-=x1-N;x1=N;}if(x0<0)x0=0;}
function zoom(f,cx){if(cx===undefined)cx=(x0+x1)/2;x0=cx-(cx-x0)*f;x1=cx+(x1-cx)*f;limita();todo();}
panels.forEach(function(p){var cv=p.cv,drag=null;
  cv.addEventListener('wheel',function(e){e.preventDefault();var r=cv.getBoundingClientRect();zoom(e.deltaY<0?0.8:1.25,p.inv(e.clientX-r.left));},{passive:false});
  cv.addEventListener('mousedown',function(e){drag={x:e.clientX,a:x0,b:x1};});
  window.addEventListener('mouseup',function(){drag=null;});
  cv.addEventListener('mousemove',function(e){var r=cv.getBoundingClientRect();
    if(drag){var dx=(e.clientX-drag.x)/(r.width-ML-MR)*(drag.b-drag.a);x0=drag.a-dx;x1=drag.b-dx;
      if(x0<0){x1-=x0;x0=0;}if(x1>N){x0-=x1-N;x1=N;}}
    cur=p.inv(e.clientX-r.left);todo();});
  cv.addEventListener('mouseleave',function(){cur=null;todo();});
  cv.addEventListener('dblclick',function(){x0=0;x1=N;todo();});});
document.getElementById('zmas').onclick=function(){zoom(0.6);};
document.getElementById('zmenos').onclick=function(){zoom(1/0.6);};
document.getElementById('ztodo').onclick=function(){x0=0;x1=N;todo();};
var sc=document.getElementById('zcurva');if(sc)sc.onchange=function(){var k=D.curvas.filter(function(c){return c.id==sc.value;})[0];if(!k)return;
  var a=k.a<=k.b?k.a:k.apice-100,b=k.a<=k.b?k.b:k.apice+100;x0=Math.max(0,a-60);x1=Math.min(N,b+60);limita();todo();};
document.getElementById('zauto').onchange=function(e){autoY=e.target.checked;todo();};
var sr=document.getElementById('zref');if(sr)sr.onchange=function(){ref=+sr.value;calcDv();todo();};
Array.prototype.forEach.call(document.querySelectorAll('#zbarra .lap'),function(s){s.onclick=function(e){
  var i=+s.getAttribute('data-i');if(e.target.tagName!=='INPUT'){s.querySelector('input').checked=!visible[i];}
  visible[i]=s.querySelector('input').checked;todo();};});
window.addEventListener('resize',todo);
if(panels.some(function(p){return p.k==='dv';}))calcDv();
todo();
})();
</script>
"""
