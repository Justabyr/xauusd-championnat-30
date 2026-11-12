import csv,json,os,time,urllib.request,datetime as dt
from pathlib import Path
from statistics import mean
URL="https://api.gold-api.com/price/XAU"
DATA=Path(os.getenv("DATA_DIR","/data"))
POLL=max(30,int(os.getenv("POLL_SECONDS","60")))
CONFIGS=[(a,b) for a in (3,5,8,10,15) for b in (20,25,30,40,50,60)]
FEE=.0004
def initial():
 return {"prices":[],"last":None,"bots":[{"id":i+1,"fast":a,"slow":b,"cash":10000.0,"oz":0.0,"peak":10000.0,"dd":0.0,"trades":0} for i,(a,b) in enumerate(CONFIGS)]}
def quote():
 req=urllib.request.Request(URL,headers={"User-Agent":"XAU-paper-championship/1.0"})
 with urllib.request.urlopen(req,timeout=20) as r: d=json.load(r)
 if d.get("symbol")!="XAU" or d.get("currency")!="USD":raise ValueError("Wrong instrument")
 p=float(d["price"]); t=dt.datetime.fromisoformat(d["updatedAt"].replace("Z","+00:00"))
 age=(dt.datetime.now(dt.timezone.utc)-t).total_seconds()
 if not (100<p<100000 and -30<=age<=180):raise ValueError("Stale/invalid quote")
 return p,t.isoformat()
def tick(s,p,t):
 if t==s["last"]:return False
 if s["prices"] and abs(p/s["prices"][-1]-1)>.1:raise ValueError("Outlier")
 for b in s["bots"]:
  if len(s["prices"])>=b["slow"]:
   bullish=mean(s["prices"][-b["fast"]:])>mean(s["prices"][-b["slow"]:])
   if bullish and b["oz"]==0:
    b["oz"]=b["cash"]/(p*(1+FEE));b["cash"]=0.;b["trades"]+=1
   elif not bullish and b["oz"]>0:
    b["cash"]=b["oz"]*p*(1-FEE);b["oz"]=0.;b["trades"]+=1
  equity=b["cash"]+b["oz"]*p
  b["peak"]=max(b["peak"],equity)
  b["dd"]=max(b["dd"],1-equity/b["peak"])
 s["prices"]=(s["prices"]+[p])[-61:];s["last"]=t
 return True
def save(s):
 DATA.mkdir(parents=True,exist_ok=True)
 temp=DATA/"state.tmp";temp.write_text(json.dumps(s));temp.replace(DATA/"state.json")
 p=s["prices"][-1]
 rows=[{"bot":b["id"],"strategy":f"MA {b['fast']}/{b['slow']}","equity_usd":round(b["cash"]+b["oz"]*p,2),"max_drawdown_pct":round(100*b["dd"],3),"trades":b["trades"]} for b in s["bots"]]
 rows.sort(key=lambda x:-x["equity_usd"])
 with (DATA/"leaderboard.tmp").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
 (DATA/"leaderboard.tmp").replace(DATA/"leaderboard.csv")
if __name__=="__main__":
 DATA.mkdir(parents=True,exist_ok=True)
 state=json.loads((DATA/"state.json").read_text()) if (DATA/"state.json").exists() else initial()
 while True:
  try:
   price,stamp=quote()
   if tick(state,price,stamp):
    save(state)
    ranked=sorted(state["bots"],key=lambda b:-(b["cash"]+b["oz"]*price))
    leader=ranked[0]
    total_trades=sum(b["trades"] for b in state["bots"])
    active_bots=sum(b["oz"]>0 for b in state["bots"])
    print(f"{stamp} XAUUSD={price:.2f} leader={leader['id']} equity={leader['cash']+leader['oz']*price:.2f} bots={len(state['bots'])} trades={total_trades} positions_open={active_bots} saved=state.json,leaderboard.csv",flush=True)
  except Exception as e:print("NO TRADE",repr(e),flush=True)
  time.sleep(POLL)
