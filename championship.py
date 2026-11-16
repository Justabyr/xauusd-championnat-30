import csv,json,os,time,urllib.request,datetime as dt,math,shutil
from pathlib import Path
from statistics import mean,pstdev
URL="https://api.gold-api.com/price/XAU"
DATA=Path(os.getenv("DATA_DIR","/data"))
POLL=max(30,int(os.getenv("POLL_SECONDS","60")))
FEE=.0004
SLIPPAGE=.0002
MAX_EXPOSURE=.25
STOP_LOSS=.02
TAKE_PROFIT=.04
CONFIGS=([( "ma_cross",a,b) for a,b in [(3,20),(5,25),(8,30),(10,40),(15,60)]]
 +[("rsi",n,k) for n,k in [(7,25),(9,30),(12,35),(14,40),(21,45)]]
 +[("breakout",n,k) for n,k in [(10,0),(15,0),(20,0),(30,0),(45,0)]]
 +[("bollinger",n,k) for n,k in [(12,1.2),(16,1.5),(20,1.8),(25,2.0),(30,2.2)]]
 +[("momentum",n,k) for n,k in [(5,.0005),(8,.001),(12,.0015),(20,.002),(30,.003)]]
 +[("macd",a,b) for a,b in [(3,10),(5,15),(8,21),(12,26),(15,35)]])
assert len(CONFIGS)==30 and len(set(CONFIGS))==30
def initial():
 return {"version":3,"prices":[],"last":None,"bots":[{"id":i+1,"kind":k,"a":a,"b":b,"cash":10000.0,"oz":0.0,"peak":10000.0,"dd":0.0,"trades":0,"entry":0.0,"fees_paid":0.0,"realized_pnl":0.0} for i,(k,a,b) in enumerate(CONFIGS)]}
def quote():
 req=urllib.request.Request(URL,headers={"User-Agent":"XAU-paper-championship/2.0"})
 with urllib.request.urlopen(req,timeout=20) as r:d=json.load(r)
 if d.get("symbol")!="XAU" or d.get("currency")!="USD":raise ValueError("Wrong instrument")
 p=float(d["price"]);t=dt.datetime.fromisoformat(d["updatedAt"].replace("Z","+00:00"))
 age=(dt.datetime.now(dt.timezone.utc)-t).total_seconds()
 if not (100<p<100000 and -30<=age<=180):raise ValueError("Stale/invalid quote")
 return p,t.isoformat()
def ema(values,n):
 alpha=2/(n+1);v=values[0]
 for x in values[1:]:v=alpha*x+(1-alpha)*v
 return v
def rsi(values,n):
 diffs=[values[i]-values[i-1] for i in range(len(values)-n,len(values))]
 gains=sum(max(x,0) for x in diffs)/n
 losses=sum(max(-x,0) for x in diffs)/n
 return 100 if losses==0 else 100-100/(1+gains/losses)
def signal(b,prices):
 k,a,c=b["kind"],b["a"],b["b"]
 if k=="ma_cross":
  if len(prices)<c+1:return None
  prev=mean(prices[-a-1:-1])-mean(prices[-c-1:-1])
  now=mean(prices[-a:])-mean(prices[-c:])
  return 1 if prev<=0<now else 0 if prev>=0>now else None
 if k=="rsi":
  if len(prices)<a+1:return None
  v=rsi(prices,a)
  return 1 if v<c else 0 if v>100-c else None
 if k=="breakout":
  if len(prices)<a+1:return None
  return 1 if prices[-1]>max(prices[-a-1:-1]) else 0 if prices[-1]<min(prices[-a-1:-1]) else None
 if k=="bollinger":
  if len(prices)<a:return None
  m=mean(prices[-a:]);sd=pstdev(prices[-a:])
  return 1 if prices[-1]<m-c*sd else 0 if prices[-1]>m+c*sd else None
 if k=="momentum":
  if len(prices)<a+1:return None
  change=prices[-1]/prices[-a-1]-1
  return 1 if change>c else 0 if change< -c else None
 if k=="macd":
  if len(prices)<c+2:return None
  before=ema(prices[:-1],a)-ema(prices[:-1],c)
  now=ema(prices,a)-ema(prices,c)
  return 1 if before<=0<now else 0 if before>=0>now else None
 raise ValueError("Unknown strategy")
def tick(s,p,t):
 if t==s["last"]:return False
 if s["prices"] and abs(p/s["prices"][-1]-1)>.1:raise ValueError("Outlier")
 prices=(s["prices"]+[p])[-200:]
 events=[]
 for b in s["bots"]:
  action=signal(b,prices)
  entry=b.get("entry",0.0)
  reason=None
  if b["oz"]>0 and entry>0:
   if p<=entry*(1-STOP_LOSS):reason="stop_loss"
   elif p>=entry*(1+TAKE_PROFIT):reason="take_profit"
  if b["oz"]>0 and (reason or action==0):
   qty=b["oz"]; execution=p*(1-SLIPPAGE)
   gross=qty*execution; fee=gross*FEE
   b["cash"]+=gross-fee;b["oz"]=0.0;b["entry"]=0.0
   b["fees_paid"]=b.get("fees_paid",0.0)+fee
   b["realized_pnl"]=b.get("realized_pnl",0.0)+(execution-entry)*qty-fee
   b["trades"]+=1
   events.append([t,b["id"],"SELL",reason or "signal",p,execution,qty,fee,b["cash"]])
  elif action==1 and b["oz"]==0 and b["cash"]>0:
   budget=b["cash"]*MAX_EXPOSURE
   execution=p*(1+SLIPPAGE)
   qty=budget/(execution*(1+FEE))
   fee=qty*execution*FEE
   b["cash"]-=qty*execution+fee;b["oz"]=qty;b["entry"]=execution
   b["fees_paid"]=b.get("fees_paid",0.0)+fee
   b["realized_pnl"]=b.get("realized_pnl",0.0)-fee
   b["trades"]+=1
   events.append([t,b["id"],"BUY","signal",p,execution,qty,fee,b["cash"]])
  equity=b["cash"]+b["oz"]*p
  b["peak"]=max(b["peak"],equity)
  b["dd"]=max(b["dd"],1-equity/b["peak"])
 s["prices"]=prices;s["last"]=t
 return events
def save_events(events):
 if not events:return
 path=DATA/"trades.csv"
 with path.open("a",newline="") as f:
  w=csv.writer(f)
  if f.tell()==0:w.writerow(["timestamp","bot","side","reason","quote","execution","quantity","fee","cash_after"])
  w.writerows(events)

def save(s):
 DATA.mkdir(parents=True,exist_ok=True)
 tmp=DATA/"state.tmp";tmp.write_text(json.dumps(s));tmp.replace(DATA/"state.json")
 p=s["prices"][-1]
 rows=[{"bot":b["id"],"strategy":f'{b["kind"]} {b["a"]}/{b["b"]}',"equity_usd":round(b["cash"]+b["oz"]*p,2),"max_drawdown_pct":round(100*b["dd"],3),"trades":b["trades"],"fees_usd":round(b.get("fees_paid",0),2),"realized_pnl_usd":round(b.get("realized_pnl",0),2)} for b in s["bots"]]
 rows.sort(key=lambda x:-x["equity_usd"])
 with (DATA/"leaderboard.tmp").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
 (DATA/"leaderboard.tmp").replace(DATA/"leaderboard.csv")
def load():
 path=DATA/"state.json"
 if not path.exists():return initial()
 s=json.loads(path.read_text())
 if s.get("version")==3:return s
 archive=DATA/"championship_previous_archive.json"
 if not archive.exists():shutil.copy2(path,archive)
 return initial()
if __name__=="__main__":
 DATA.mkdir(parents=True,exist_ok=True)
 state=load()
 while True:
  try:
   price,stamp=quote()
   if stamp!=state["last"]:
    events=tick(state,price,stamp)
    save_events(events)
    save(state)
    ranked=sorted(state["bots"],key=lambda b:-(b["cash"]+b["oz"]*price))
    leader=ranked[0]
    print(f'{stamp} XAUUSD={price:.2f} leader={leader["id"]} equity={leader["cash"]+leader["oz"]*price:.2f} bots={len(state["bots"])} trades={sum(b["trades"] for b in state["bots"])} positions_open={sum(b["oz"]>0 for b in state["bots"])} saved=state.json,leaderboard.csv',flush=True)
  except Exception as e:print("NO TRADE",repr(e),flush=True)
  time.sleep(POLL)
