# Accounts

Drop one session file per FirstCry login in here:

```
accounts/samir.json
accounts/priya.json
```

The filename becomes the account name, and it appears on every alert so you
know which login a notification is about.

Each account gets:

- its own state file (`state/wishlist_<name>.json`), so baselines never mix
- its own thread, so a slow or expired account never holds up the others
- deliverability read from **its own cart**, which uses whatever delivery
  address that account has saved on FirstCry

## Creating one

```bash
python import_cookies.py          # log in as that account, paste the cURL
mv session.json accounts/samir.json
```

Repeat per account. Log out and back in as the other person in between, or
use a private window, so you capture the right session each time.

## If this folder is empty

The bot falls back to a single `session.json` in the project root. Existing
single-account setups keep working with no changes.

## Different pincodes

Deliverability comes from each account's own cart, so two accounts with
different delivery addresses just work.

The only thing that needs telling is the shortlist lookup, which takes a
pincode directly. Override it per account in `.env`:

```
PINCODE_PRIYA=400001
```

The name matches the filename, uppercased. Without an override it uses the
global `PINCODE`.

## Never commit these files

`accounts/*.json` is gitignored. Each one is a live login - anyone holding
it is signed in as that person.
