# FirstCry Hot Wheels Bots

Two bots that watch FirstCry for you.

| Bot | What it does | How often | Login |
|-----|--------------|-----------|-------|
| **Bot 1** | Tells you when a **new Hot Wheels item** is listed | Once a day | Not needed |
| **Bot 2** | Watches your **shortlist**, alerts when an item becomes **deliverable to your pincode** | Every 15s | Required |

---

## Quick start (fresh clone)

```bash
git clone https://github.com/Samir-477/firstcry_bot.git
cd firstcry_bot
```

**Linux / macOS**
```bash
bash install.sh
```

**Windows**
```
install.bat
```

That creates a virtualenv, installs the two dependencies, and checks your
setup. It will tell you if anything is missing.

Then three one-time steps:

```bash
cp .env.example .env         # copy .env.example to .env on Windows
python setup_telegram.py     # creates the Telegram link, finds your chat ID
python import_cookies.py     # logs you into FirstCry (see below)
```

Set `PINCODE` in `.env` to your own, then:

```bash
python run_all.py
```

### Dependencies

Just two, both pure Python - no browser, no system packages:

```
requests
python-dotenv
```

### What is NOT in this repo

`.env`, `session.json` and `state/` are gitignored. The first two are
secrets, the third regenerates itself. You create them with the commands
above.

---

## How it works (plain English)

Both bots run the same loop: **wake up -> look -> compare to last time -> alert only if changed -> remember.**

The "remember" step is what stops you being spammed. Each bot keeps a small
memory file in `state/`. On the very first run it just fills that file and stays
silent - otherwise you'd get 140 notifications on day one.

### Bot 1 doesn't scrape the website

FirstCry's pages are just a shell; the products come from a private JSON API
that their own site calls in the background. Bot 1 calls that same API directly.
That means each check takes about 10 seconds instead of a minute, uses almost no
memory, and needs no browser and no login.

Hot Wheels is brand ID `113` on FirstCry - currently 140 products.

---

## Setup

### 1. Install
```bash
pip install -r requirements.txt
```

### 2. Telegram alerts
- Open Telegram, message **@BotFather**, send `/newbot`, follow the prompts
- Copy the token it gives you (looks like `8123456789:AAH...`)
- Message **@userinfobot** - it replies with your numeric chat ID
- Put both into `.env`

### 3. Run Bot 1
```bash
python bot1_new_arrivals.py          # check once now
python bot1_new_arrivals.py --loop   # keep running, checks daily
python bot1_new_arrivals.py --reset  # forget everything and re-seed
```

### 4. Run Bot 2
```bash
python bot2_wishlist.py          # check once now
python bot2_wishlist.py --loop   # keep running, checks every 60s
python bot2_wishlist.py --reset  # clear state and re-seed
```

Bot 2 keeps your whole shortlist parked in the cart and watches it:

| Step | What happens |
|------|--------------|
| **Add** (every 5 checks) | Any shortlist item not in the cart gets added. FirstCry accepts whatever is in stock and silently refuses the rest. |
| **Watch** (every check) | The cart is re-read. Every row carries `IsServicable` - 0 means "cannot be delivered to your pincode", above 0 means it can. Any item that flips gets a Telegram. |

**Nothing is ever removed from the cart.** Deliverability is only visible for
items sitting in it, so an item taken out stops being watched. A cart showing
"Undeliverable" rows is not a bug - those are the ones still being waited on.

It never buys anything. Adding to the cart is as far as it goes.

### Two things that cost me a while

**The cart is the only trustworthy source.** FirstCry exposes
`/tatapi/oam/checkdeliveryinfo`, which looks like it answers "can this reach
my pincode" without touching the cart. It was tried and removed: it returned
0 three times running for a product the cart was actively shipping. Its
batched `groupserviceability` field is worse still - it reported 1 for items
the cart refused to deliver.

**Cart writes get dropped when fired back-to-back.** Sending 24 in a tight
loop left a third of them silently unapplied. All cart writes are now paced,
verified against a fresh read, and retried if they did not take.

### 5. Log in (only needed for Bot 2)
A real Chrome window opens. **You** log in by hand - password, OTP, whatever
FirstCry asks. The script never types or stores your password. It saves only
your session cookies to `session.json`.

### 6. Check you're logged in
```bash
python check_session.py
```
Says `LOGGED IN` or `SESSION EXPIRED` in plain English. Run it any time.

When that session eventually expires, Bot 2 will Telegram you, and you just run
`import_cookies.py` again.

---

## How login actually works

Your password is used **once**, by you, in a real browser. FirstCry then hands
back a **session cookie** - a long random string that proves who you are. That
cookie, not your password, is what identifies you on every later request.

`session.json` holds that cookie. When you deploy, you copy that one file to the
server:

```
LAPTOP                              SERVER
  import_cookies.py                   bot2.py
  you log in by hand                  loads session.json
  FirstCry returns cookie             sends cookie on every request
  saved to session.json  ──copy──►    FirstCry: "this is you" OK
```

The server needs no screen, no browser, and no password.

---

## Running both bots at once

```bash
python run_all.py
```

Or just double-click **start_bots.bat**.

Bot 1 and Bot 2 each run on their own thread, so a slow check in one never
delays the other. Ctrl+C stops both. Bot 2 keeps quiet unless something
happens, with a short heartbeat every 30 minutes so you can see it's alive.

If `session.json` is missing it starts Bot 1 alone rather than failing.

### Starting automatically with Windows

Press `Win+R`, type `shell:startup`, press Enter, and drop a shortcut to
`start_bots.bat` into that folder. The bots then start whenever you log in.

## Files

| File | Purpose |
|------|---------|
| `config.py` | Reads settings from `.env` |
| `firstcry_api.py` | Talks to FirstCry's product API |
| `notifier.py` | Sends Telegram alerts |
| `bot1_new_arrivals.py` | Bot 1 |
| `import_cookies.py` | **Easiest login route** - paste a cURL from DevTools |
| `check_session.py` | Tells you if the session is still valid |
| `firstcry_account.py` | Logged-in client: reads wishlist/cart, adds to cart |
| `bot2_wishlist.py` | Bot 2 |
| `run_all.py` | Runs both bots together |
| `start_bots.bat` | Double-click launcher for Windows |
| `state/` | The bots' memory files |

---

## Security

`.env`, `session.json` and `state/` are all in `.gitignore`.

**`session.json` is as good as being logged in as you** - don't share it, don't
upload it, don't commit it. Your password is never stored anywhere by these bots.
