#!/bin/python
import asyncio, datetime, json, random, requests, sys, time, websockets
from aioconsole import aprint

with open("data.json") as f:
    data: dict[str] = json.load(f)

SYSTEM = "\033[35;1m"
OSYSTEM = "\033[33;1m"
CHAT = "\033[32m"
VOTE = "\033[31;1m"
QUOTE = "\033[34m"
BOLD = "\033[1m"
RESET = "\033[0m"

usermap = {}
pupmap = {}
playermap = {}
messages = {}
votes = {}
swn = set()
swbl = set()
afk = False
pss = -1
grs = True
newroom = 0
st = False
tasks: list[asyncio.Task] = []

username = sys.argv[1] if len(sys.argv) > 1 else input("Username: ")
password = sys.argv[2] if len(sys.argv) > 2 else input("Password: ")
roomname = sys.argv[3] if len(sys.argv) > 3 else input("Room Name: ")
groomid = sys.argv[4] if len(sys.argv) > 4 else None

session = requests.post("https://mafia.gg/api/user-session", headers={"Content-Type": "application/json", "User-Agent": "hi mgg mods sorry for the trouble ive caused over the year"}, json={"login": username, "password": password})
if session.status_code != 200:
  quit(1)
token = session.cookies["userSessionToken"]
userid = session.json()["id"]

mid = requests.post("https://mafia.gg/api/rooms/", json={"name": roomname, "unlisted": False}, headers={"Cookie": f"userSessionToken={token}"}).json()["id"] if groomid is None else groomid
room = requests.get(f"https://mafia.gg/api/rooms/{mid}", headers={"Cookie": f"userSessionToken={token}"})
auth = room.json()["auth"]

if groomid is not None:
  newroom = time.time()

def players(pup: dict):
  return sum([1 for i in pup.values() if i])

def options(code: str, start: str = None):
  global roomname
  opt = {"type": "options", "roomName": roomname, "unlisted": False, "deck": "-1", "dayLength": 5, "nightLength": 2, "scaleTimer": False, "disableVoteLock": True, "revealSetting": "allReveal", "mustVote": False, "majorityRule": "51", "twoKp": "0", "deadlockPreventionLimit": "5", "hostRoleSelection": False, "hideSetup": False, "noNightTalk": False}
  if start is None:
    opt["roles"] = dict(map(lambda x:str.split(x, "a"), str.split(code, "b")))
  else:
    opt["roles"] = dict(map(lambda x:str.split(x, "a"), str.split(data["setups"][code]["code"], "b")))
  opt["dayStart"] = start if start is not None else "dawnStart"
  return opt

async def fit(ws):
  global pupmap, swn, votes, pss, grs, afk, newroom
  count = max(len(swn) + players(pupmap), 3) - 3
  rs = sum(votes.values()) > 0
  if (pss == count and grs == rs) or afk or newroom + 20 > time.time():
    return
  if rs:
    setup = random.choice(data["presets"]["real"][count])
    await ws.send(json.dumps(options(setup, data["setups"][setup]["start"])))
  else:
    setup = data["presets"]["randumbs"][count]
    await ws.send(json.dumps(options(setup)))
  pss = count
  grs = rs
  if not afk and len(swn) == 0 and players(pupmap):
    afk = True
    await ws.send(json.dumps({"type": "readyCheck"}))

async def efit(ws):
  await asyncio.sleep(15)
  await fit(ws)

async def parse(i, ws):
  global usermap, playermap, messages, swn, swbl, afk, votes, st, mid
  try:
    mtimestamp = datetime.datetime.fromtimestamp(i["timestamp"]).strftime("%I:%M:%S %p")
  except KeyError:
    return
  if i["type"] == "chat":
    mmessage = i["message"]
    if i["from"]["model"] == "user":
      muserid = i["from"]["userId"]
      await aprint(f"{CHAT}[{mtimestamp}] {usermap[muserid]} said: {mmessage}{RESET}", flush=True)
      if mmessage.lower() == "/vote rd":
        votes[muserid] = -1
      elif mmessage.lower() == "/vote rs":
        votes[muserid] = 1
      elif mmessage.lower() == "/vote uv":
        votes[muserid] = 0
      elif mmessage.lower().startswith("/kick ") and usermap[muserid] in data["trusted"]:
        mkickid = int(mmessage[6:])
        requests.post(f"https://mafia.gg/api/rooms/{mid}/kick", json={"userId": mkickid}, headers={"Cookie": f"userSessionToken={token}"})
      elif mmessage.lower() == "/transfer" and usermap[muserid] in data["trusted"]:
        await ws.send(json.dumps({"type": "transferHost", "userId": muserid}))
      await fit(ws)
    else:
      mplayerid = i["from"]["playerId"]
      mquote = f"> [{mtimestamp}] {playermap[mplayerid]} said: {mmessage}{RESET}"
      messages[i["qid"]] = mquote
      await aprint(f"{CHAT}{BOLD}[{mtimestamp}] {playermap[mplayerid]} said: {mmessage}{RESET}", flush=True)
  elif i["type"] == "system":
    mmessage = i["message"]
    await aprint(f"{SYSTEM}[{mtimestamp}] {mmessage}{RESET}", flush=True)
    if mmessage == "All players have readied up!":
      afk = False
      await ws.send(json.dumps({"type": "startGame"}))
    elif mmessage == "The Ready Check has ended.":
      afk = False
      await fit(ws)
    elif mmessage == "This room will be automatically closed in 2 minutes if the game does not begin":
      maroom = requests.post("https://mafia.gg/api/rooms/", json={"name": roomname, "unlisted": False}, headers={"Cookie": f"userSessionToken={token}"})
      mroomid = maroom.json()["id"]
      return mroomid
  elif i["type"] == "startGame":
    mphase = i["time"]["phase"]
    for j in i["players"]:
      playermap[j["playerId"]] = j["name"]
    await aprint(f"{OSYSTEM}[{mtimestamp}] Game started on {mphase}!{RESET}", flush=True)
    st = True
  elif i["type"] == "decision":
    if i["details"]["text"] == "votes":
      mvoter = playermap[i["details"]["playerId"]]
      if i["details"]["targetPlayerId"] == "n":
        messages[i["qid"]] = f"{VOTE}> [{mtimestamp}] {mvoter} votes for no condemn{RESET}"
        await aprint(f"{VOTE}[{mtimestamp}] {mvoter} votes for no condemn{RESET}", flush=True)
      else:
        mvotee = playermap[i["details"]["targetPlayerId"]]
        messages[i["qid"]] = f"{VOTE}> [{mtimestamp}] {mvoter} votes {mvotee}{RESET}"
        await aprint(f"{VOTE}[{mtimestamp}] {mvoter} votes {mvotee}{RESET}", flush=True)
    elif i["details"]["text"] == "has unvoted":
      mvoter = playermap[i["details"]["playerId"]]
      messages[i["qid"]] = f"{VOTE}> [{mtimestamp}] {mvoter} unvotes{RESET}"
      await aprint(f"{VOTE}[{mtimestamp}] {mvoter} unvotes{RESET}", flush=True)
  elif i["type"] == "quote":
    mqid = i["qid"]
    if i["from"]["model"] == "user":
      muserid = i["from"]["userId"]
      await aprint(f"{QUOTE}[{mtimestamp}] {usermap[muserid]} quotes\n{BOLD}{messages[mqid]}{RESET}", flush=True)
    else:
      mplayerid = i["from"]["playerId"]
      await aprint(f"{QUOTE}{BOLD}[{mtimestamp}] {playermap[mplayerid]} quotes\n{messages[mqid]}{RESET}", flush=True)
  elif i["type"] == "time":
    mphase = i["phase"]
    mnum = i["ordinal"]
    await aprint(f"{OSYSTEM}[{mtimestamp}] It is now {mphase.capitalize()} {mnum}!{RESET}", flush=True)
  elif i["type"] == "userJoin":
    muserid = i["userId"]
    if muserid not in usermap.keys():
      musername = requests.get(f"https://mafia.gg/api/users/{muserid}").json()[0]["username"]
      usermap[muserid] = musername
      votes[muserid] = 0
      pupmap[muserid] = False
    await aprint(f"{OSYSTEM}[{mtimestamp}] {usermap[muserid]} joined!{RESET}", flush=True)
    if muserid not in swbl and not st:
        swn.add(muserid)
        await fit(ws)
        await asyncio.sleep(10)
        if muserid in swn:
            swn.remove(muserid)
            swbl.add(muserid)
            await fit(ws)
  elif i["type"] == "userQuit":
    muserid = i["userId"]
    await aprint(f"{OSYSTEM}[{mtimestamp}] {usermap[muserid]} left!{RESET}", flush=True)
  elif i["type"] == "endGame":
    await aprint(f"{OSYSTEM}[{mtimestamp}] Game ended!{RESET}", flush=True)
    await asyncio.sleep(3)
    maroom = requests.post("https://mafia.gg/api/rooms/", json={"name": roomname, "unlisted": False}, headers={"Cookie": f"userSessionToken={token}"})
    mroomid = maroom.json()["id"]
    await ws.send(json.dumps({"type": "newGame", "roomId": mroomid}))
    return mroomid
  elif i["type"] == "userUpdate":
    muserid = i["userId"]
    pupmap[muserid] = i["isPlayer"]
    await fit(ws)
  return None

async def peek(user, room, auth):
  global usermap, pupmap, st, votes, tasks
  async with websockets.connect("wss://mafia.gg:443/engine") as ws:
    await ws.send(json.dumps({"type": "clientHandshake", "userId": user, "roomId": room, "auth": auth}))
    info = await ws.recv()
    await ws.send(json.dumps({"type": "presence", "isPlayer": False}))
    await ws.send(json.dumps({"type": "chat", "message": "This is a bot. /vote RD for randoms, /vote RS for real setups, /vote UV to unvote!"}))
    await fit(ws)
    info = json.loads(info)
    possibles = ",".join([str(i) for i in info["possibleUserIds"]])
    userinfo = requests.get(f"https://mafia.gg/api/users/{possibles}").json()
    for i in userinfo:
      usermap[i["id"]] = i["username"]
      votes[i["id"]] = 0
    for i in info["users"]:
      pupmap[i["userId"]] = i["isPlayer"]
    for i in info["events"]:
      if i["type"] == "startGame":
        st = True
    mtimestamp = datetime.datetime.now().strftime("%I:%M:%S %p")
    musers = ", ".join(usermap.values())
    await aprint(f"{OSYSTEM}[{mtimestamp}] Users: {musers}{RESET}", flush=True)
    asyncio.create_task(efit(ws))
    while True:
      packet = json.loads(await ws.recv())
      tasks.append(asyncio.create_task(parse(packet, ws)))
      temp = []
      for i in tasks:
        if i.done() and i.result() is not None:
          return i.result()
        elif not i.done():
          temp.append(i)
      tasks = temp

while True:
  mtimestamp = datetime.datetime.now().strftime("%I:%M:%S %p")
  print(f"{OSYSTEM}[{mtimestamp}] Joining https://mafia.gg/game/{mid}{RESET}")
  mid = asyncio.run(peek(userid, mid, auth))
  tasks.clear()
  newroom = time.time()
  messages.clear()
  playermap.clear()
  swbl.clear()
  pss = -1
  st = False
