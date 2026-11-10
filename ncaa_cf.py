###################################################################
# NCAA Cloudflare-resilient JSON session (same technique as NAIA) #
#                                                                 #
# The NCAA data API (https://sdataprod.ncaa.com/) is a JSON       #
# GraphQL endpoint. Plain `requests` works from a residential IP, #
# but Cloudflare blocks it by TLS fingerprint / rate / data-center#
# IP once volume picks up (403 / 429 / 503 / "just a moment").    #
#                                                                 #
# This is the SAME bypass NAIA uses (naia_fast_cf.py), adapted    #
# for a JSON API instead of HTML pages:                           #
#                                                                 #
#   1. FAST PATH - curl_cffi with Chrome TLS impersonation. A     #
#      real-Chrome TLS fingerprint alone defeats the most common  #
#      block, with NO browser needed. This is the default and is  #
#      as fast as plain requests.                                 #
#   2. SELF-HEAL - on a 403/429/503/challenge it LAZILY opens a   #
#      headful Chrome (Playwright, persistent profile so the      #
#      clearance stays warm), passes Cloudflare (solve the box by #
#      hand if one ever shows), mints the cf_clearance cookie,    #
#      hands it + the exact User-Agent back to curl_cffi, and     #
#      retries the SAME url - never skipping data.                #
#   3. BROWSER FALLBACK - if the site binds cf_clearance to the   #
#      browser's TLS fingerprint (the curl_cffi handoff fails,    #
#      like the NAIA PrestoSports site does), it transparently    #
#      fetches the JSON by navigating the real browser instead.   #
#   4. ATTACH - connect to a real Chrome you opened on a debug    #
#      port (--attach), solve the box once by hand; best for      #
#      data-center / VPN situations (residential IP passes).      #
#                                                                 #
# Returns a tiny requests-like object (.status_code/.text/.json())#
# so it drops straight into the existing scrapers.                #
###################################################################

import json
import time
import random

from curl_cffi import requests as creq

CF_MARKERS = ("just a moment", "attention required", "cf-chl", "verifying you are human",
              "needs to review the security", "enable javascript and cookies",
              "cf-browser-verification", "challenge-platform")

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# A real sdataprod JSON url used purely to mint a cf_clearance cookie for the
# api host. Any valid boxscore url works; this one is a known-good contest.
MINT_URL = ("https://sdataprod.ncaa.com/?meta=NCAA_GetGamecenterBoxscoreBasketballById_web"
            "&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A"
            "%224a7fa26398db33de3ff51402a90eb5f25acef001cca28d239fe5361315d1419a%22%7D%7D"
            "&variables=%7B%22contestId%22%3A%226314051%22%2C%22staticTestEnv%22%3Anull%7D")


class CFResponse:
    """Minimal requests-like response so this drops into existing code."""
    def __init__(self, text, status_code):
        self.text = text
        self.status_code = status_code

    def json(self):
        return json.loads(self.text)


class CFSession:
    """Cloudflare-resilient JSON GET session.

    Default: curl_cffi (Chrome impersonation), no browser. A browser is only
    started (or attached) when a real block is hit, or up-front if you pass
    headful=True / attached=True.
    """

    def __init__(self, headers=None, min_interval=1.0, refresh_every=0,
                 impersonate="chrome", profile_dir="ncaa_cf_profile",
                 headful=False, attached=False, cdp_url="http://localhost:9222",
                 retries=4, verbose=True):
        self.base_headers = headers or {
            "User-Agent": DEFAULT_UA,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.ncaa.com/",
            "Origin": "https://www.ncaa.com",
        }
        self.ua = self.base_headers.get("User-Agent", DEFAULT_UA)
        self.cf_cookies = {}
        self._impersonate = impersonate
        self.min_interval = min_interval
        self.refresh_every = refresh_every     # 0 = off
        self.retries = retries
        self.verbose = verbose

        self.profile_dir = profile_dir
        self.want_headful = headful
        self.attached = attached
        self.cdp_url = cdp_url

        # Escalating cooldowns (seconds) for own-browser/curl mode - we wait and
        # retry the SAME url instead of skipping, so no games are lost.
        self.block_waits = [20, 45, 90, 180, 300, 300, 300, 300]

        # Browser handles (created lazily).
        self._pw = None
        self._ctx = None
        self._page = None
        self._owns_browser = False
        self.browser_fetch_only = False   # set if curl_cffi handoff fails

        self._last_req = 0.0
        self._last_refresh = 0.0
        self._req_count = 0
        self._refresh_count = 0

        if self.attached or self.want_headful:
            self._ensure_browser()
            self.mint_clearance()

    # ---------- logging ----------
    def _log(self, msg):
        if self.verbose:
            print(msg, flush=True)

    # ---------- challenge detection ----------
    @staticmethod
    def _looks_like_challenge(text):
        if not text:
            return False
        low = text.lower()
        # A genuine JSON API response starts with { or [ - never a challenge.
        head = low.lstrip()[:1]
        if head in ("{", "["):
            return False
        return any(m in low for m in CF_MARKERS)

    # ---------- browser lifecycle (lazy) ----------
    def _ensure_browser(self):
        if self._page is not None:
            return
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        if self.attached:
            self._log(f"[CF] Attaching to Chrome at {self.cdp_url} ...")
            browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
            self._ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
            self._owns_browser = False
        else:
            import os
            profile = os.path.abspath(self.profile_dir)
            self._log(f"[CF] Opening headful Chrome (profile: {profile}) to pass Cloudflare ...")
            self._ctx = self._pw.chromium.launch_persistent_context(
                user_data_dir=profile, headless=False,
                args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
                locale="en-US", no_viewport=True,
            )
            self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
            self._owns_browser = True

    def _read_session(self):
        cookies = self._ctx.cookies()
        try:
            ua = self._page.evaluate("() => navigator.userAgent")
        except Exception:
            ua = None
        return cookies, ua

    def _store_session(self, cookies, ua, quiet=False):
        self.cf_cookies = {c["name"]: c["value"] for c in cookies}
        if ua:
            self.ua = ua
            self.base_headers["User-Agent"] = ua
        if not quiet:
            names = ", ".join(sorted(self.cf_cookies.keys())) or "(none)"
            self._log(f"[CF] cookies: {names}")

    def _wait_until_cleared(self, budget):
        """Wait for the open page to show JSON / no challenge."""
        waited = 0
        while waited < budget:
            time.sleep(3)
            waited += 3
            try:
                body = self._page.evaluate("() => document.body ? document.body.innerText : ''")
            except Exception:
                continue
            if body and not self._looks_like_challenge(body):
                return True
            if waited % 30 == 0:
                self._log(f"  [CF] still verifying... ({waited}s of {budget}s) "
                          f"- solve the box in the window if it appears")
        return False

    def mint_clearance(self, max_wait=300):
        """Pass Cloudflare in the browser and store cookies + UA."""
        self._ensure_browser()
        self._log("[CF] passing Cloudflare in the browser (solve the box if one appears)...")
        try:
            self._page.goto(MINT_URL, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            self._log(f"  [CF] nav: {e}")
        self._wait_until_cleared(max_wait)
        cookies, ua = self._read_session()
        self._store_session(cookies, ua)
        self._last_refresh = time.time()

    def _refresh_clearance(self, force=False):
        now = time.time()
        if not force and now - self._last_refresh < 6:
            time.sleep(1.5)
            return
        self._ensure_browser()
        self._refresh_count += 1
        budget = 300 if self.attached else 120
        self._log(f"  [CF] re-verifying in the Chrome window (#{self._refresh_count}) "
                  f"- up to {budget // 60} min; solve the box if it appears...")
        try:
            try:
                self._page.reload(timeout=60000, wait_until="domcontentloaded")
            except Exception:
                self._page.goto(MINT_URL, timeout=60000, wait_until="domcontentloaded")
            self._wait_until_cleared(budget)
            cookies, ua = self._read_session()
            self._store_session(cookies, ua, quiet=True)
        except Exception as e:
            self._log(f"  [CF] refresh issue (continuing with current cookie): {e}")
        self._last_refresh = time.time()

    # ---------- throttle ----------
    def _throttle(self):
        now = time.time()
        wait = self.min_interval - (now - self._last_req)
        if wait > 0:
            time.sleep(wait)
        time.sleep(random.uniform(0, 0.3))
        self._last_req = time.time()

    # ---------- browser JSON fetch (fallback / attach) ----------
    def _browser_get(self, url, timeout=30):
        self._ensure_browser()
        self._throttle()
        attempts = 0
        while attempts < 6:
            attempts += 1
            try:
                resp = self._page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                status = resp.status if resp else 0
                body = self._page.evaluate("() => document.body ? document.body.innerText : ''")
                if self._looks_like_challenge(body) or status in (403, 429, 503):
                    self._log(f"  [CF] challenge on this url - waiting up to 5 min "
                              f"(solve the box in the window if it appears)...")
                    if not self._wait_until_cleared(300):
                        self._log("  [CF] not cleared in 5 min - re-navigating...")
                        continue
                    body = self._page.evaluate("() => document.body ? document.body.innerText : ''")
                    status = 200
                if status == 404:
                    return CFResponse(body, 404)
                return CFResponse(body, 200)
            except Exception as e:
                self._log(f"  [nav retry {attempts}/6] {e}")
                time.sleep(2)
        return None

    # ---------- the one networking method ----------
    def get(self, url, headers=None, timeout=30):
        """Cloudflare-resilient GET. Returns CFResponse or None.

        On a block it WAITS + re-verifies and retries the SAME url, never
        skipping. Drop-in for `requests.get(url, headers=..., timeout=...)`."""
        if self.browser_fetch_only:
            return self._browser_get(url, timeout)

        req_headers = dict(self.base_headers)
        if headers:
            req_headers.update(headers)
        req_headers["User-Agent"] = self.ua

        block_idx = 0
        transient = 0
        while True:
            self._throttle()
            try:
                r = creq.get(url, impersonate=self._impersonate, headers=req_headers,
                             cookies=self.cf_cookies, timeout=timeout)
                blocked = r.status_code in (403, 429, 503) or self._looks_like_challenge(r.text)
                if r.status_code == 200 and not blocked:
                    self._req_count += 1
                    if self.refresh_every and self._page is not None \
                            and self._req_count % self.refresh_every == 0:
                        self._log(f"  [CF] proactive token refresh after {self._req_count} requests...")
                        self._refresh_clearance(force=True)
                    return CFResponse(r.text, 200)
                if r.status_code == 404:
                    return CFResponse(r.text, 404)
                if blocked:
                    block_idx += 1
                    self._log(f"  [CF] blocked on {url[:80]}... (status {r.status_code}, attempt {block_idx})")
                    # First block: bring up the browser and mint a real clearance,
                    # then try the curl_cffi handoff before any long cooldown.
                    if self._page is None:
                        self._log("  [CF] escalating to a real browser to pass Cloudflare...")
                        self.mint_clearance()
                        continue
                    # Browser is up. Re-verify, then test whether curl_cffi can
                    # reuse the cookie. If not, the site is TLS-binding it - fall
                    # back to fetching JSON through the browser (like NAIA).
                    self._refresh_clearance(force=True)
                    probe = creq.get(url, impersonate=self._impersonate, headers=req_headers,
                                     cookies=self.cf_cookies, timeout=timeout)
                    if probe.status_code == 200 and not self._looks_like_challenge(probe.text):
                        return CFResponse(probe.text, 200)
                    if block_idx >= 2:
                        self._log("  [CF] curl_cffi can't reuse this clearance "
                                  "(TLS-bound) - switching to browser-navigation fetch.")
                        self.browser_fetch_only = True
                        self.min_interval = max(self.min_interval, 1.5)
                        return self._browser_get(url, timeout)
                    wait = self.block_waits[min(block_idx - 1, len(self.block_waits) - 1)]
                    self._log(f"  [CF] cooling down {wait}s, then retrying (not skipping)...")
                    time.sleep(wait)
                    self.min_interval = min(self.min_interval + 0.3, 4.0)
                    continue
                transient += 1
                self._log(f"  [WARN] {url[:80]}... -> status {r.status_code} (try {transient}/{self.retries})")
            except Exception as e:
                transient += 1
                self._log(f"  [RETRY {transient}/{self.retries}] {e}")
            if transient >= self.retries:
                return None
            time.sleep(1 + random.uniform(0, 1))

    # ---------- cleanup ----------
    def close(self):
        if self._owns_browser and self._ctx is not None:
            try:
                self._ctx.close()
            except Exception:
                pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._pw = self._ctx = self._page = None
