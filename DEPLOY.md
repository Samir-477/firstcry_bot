# Deploying to Oracle Cloud (Always Free)

End result: the bots run 24/7 on a free Linux VM, restart themselves if they
crash, and come back automatically after a reboot.

Budget about an hour, most of it Oracle's signup.

---

## 1. Sign up

https://signup.oraclecloud.com

- Pick **India (Mumbai or Hyderabad)** as your home region. You cannot change
  this later, and it decides where your free VM can live.
- A credit/debit card is required for identity verification. Oracle places a
  temporary hold (about Rs 80) and refunds it. **Always Free resources are
  never charged** - but see the warning in section 8.
- Verification can take anywhere from minutes to a day.

## 2. Create the VM

Console → **Compute** → **Instances** → **Create instance**

| Setting | Choose |
|---------|--------|
| Image | **Ubuntu 22.04** (or 24.04) |
| Shape | **VM.Standard.E2.1.Micro** (AMD, 1 GB RAM) |
| SSH keys | **Generate a key pair** and DOWNLOAD both files |

### Take the AMD micro, not the ARM shape

Oracle's headline free tier is a 4-core / 24 GB **Ampere ARM** machine, and
everyone tries to grab it. In Indian regions it very often fails with
"Out of capacity", sometimes for weeks.

The **AMD E2.1.Micro** (1 GB RAM) is almost always available, and these bots
use around 40 MB. Do not waste an afternoon fighting for the ARM box you do
not need.

### Networking

Accept the defaults - a public IP is assigned automatically.

**You do not need to open any ports.** The bots only make outbound calls to
FirstCry and Telegram. Nothing needs to reach them. Leaving inbound closed
(except SSH) is exactly right.

## 3. Connect

Note the instance's **Public IP address** from the console.

The downloaded private key needs restricted permissions or SSH refuses it.

**Windows PowerShell:**
```powershell
icacls .\ssh-key.key /inheritance:r
icacls .\ssh-key.key /grant:r "$env:USERNAME:(R)"
ssh -i .\ssh-key.key ubuntu@YOUR_PUBLIC_IP
```

**Git Bash:**
```bash
chmod 600 ssh-key.key
ssh -i ssh-key.key ubuntu@YOUR_PUBLIC_IP
```

The default username on Oracle's Ubuntu images is `ubuntu`.

## 4. Copy the project up

From your laptop, in the folder ABOVE `first_cry`:

```bash
scp -i ssh-key.key -r first_cry ubuntu@YOUR_PUBLIC_IP:~/
```

`.gitignore` does not apply to `scp`, so this copies `.env`, `session.json`
and `state/` too - which is what you want here. Those three files are the
only things that cannot be regenerated on the server.

## 5. Run the setup script

```bash
ssh -i ssh-key.key ubuntu@YOUR_PUBLIC_IP
bash ~/first_cry/deploy/setup.sh
```

It installs Python, creates a virtualenv, checks your session is still valid,
installs a systemd service, and starts it.

If it reports the session is dead, run `import_cookies.py` on your laptop
again and re-copy `session.json`.

## 6. Verify

```bash
sudo systemctl status firstcry-bots     # should say "active (running)"
journalctl -u firstcry-bots -f          # live logs, Ctrl+C to stop watching
```

You want to see the startup banner and then Bot 2's checks ticking.

You should also get a Telegram snapshot on first start.

## 7. Day-to-day

| Task | Command |
|------|---------|
| Live logs | `journalctl -u firstcry-bots -f` |
| Restart | `sudo systemctl restart firstcry-bots` |
| Stop | `sudo systemctl stop firstcry-bots` |
| Edit settings | `nano ~/first_cry/.env` then restart |
| Update code | `scp` the changed files up, then restart |

**Any change to `.env` or the code needs a restart.** Python reads both once
at startup.

### When the session expires

Bot 2 will Telegram you "FirstCry session expired" and stop.

1. On your laptop: `python import_cookies.py`
2. `scp -i ssh-key.key first_cry/session.json ubuntu@YOUR_IP:~/first_cry/`
3. `ssh ... "sudo systemctl restart firstcry-bots"`

Expect this every few weeks.

## 8. The one real warning

Oracle **reclaims idle Always Free compute**. Their stated rule is roughly:
under 20% CPU, under 20% network, and low memory use over a 7-day window.

These bots are almost entirely idle, so a permanently-free VM running only
this is a genuine candidate for reclamation.

Two ways to handle it:

- **Upgrade to Pay As You Go.** Always Free resources stay free, and PAYG
  accounts are exempt from idle reclamation. You are only billed if you
  create something outside the free tier. This is the usual advice.
- **Accept the risk.** If the VM disappears, recreate it and re-run
  `setup.sh`. Everything except `.env` and `session.json` is reproducible.

Do not add a fake CPU-burning loop to dodge this - it wastes power and
breaks the spirit of the free tier.

## Alternative if Oracle frustrates you

Hetzner CX22 (about Rs 400/month) takes five minutes end to end and has no
capacity games or reclamation policy. The same `setup.sh` works unchanged.
