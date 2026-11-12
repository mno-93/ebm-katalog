"""Minimaler JSF/PrimeFaces-Client für ebm.kbv.de (Session-Cookie + ViewState)."""
import http.cookiejar, re, time, urllib.parse, urllib.request

BASE = "https://ebm.kbv.de"
UA = "Mozilla/5.0 (Macintosh) EBM-Abzug/0.1"


class JSF:
    def __init__(self, delay=0.4):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.vs, self.delay, self.page = None, delay, None

    def _req(self, path, data=None, ajax=False):
        time.sleep(self.delay)
        h = {"User-Agent": UA}
        if ajax:
            h.update({"Faces-Request": "partial/ajax", "X-Requested-With": "XMLHttpRequest",
                      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        r = self.op.open(urllib.request.Request(BASE + path, body, h), timeout=60)
        return r.read().decode("utf-8")

    def get(self, path="/index.xhtml"):
        self.page = self._req(path)
        self.path = path
        self._vs(self.page)
        return self.page

    def _vs(self, txt):
        m = re.search(r'javax\.faces\.ViewState[^>]*value="([^"]+)"', txt) or \
            re.search(r'<update id="[^"]*javax\.faces\.ViewState[^"]*"><!\[CDATA\[(.*?)\]\]>', txt)
        if m:
            self.vs = m.group(1)

    def ajax(self, form, source, event="action", process=None, update="@all", extra=None):
        d = {"javax.faces.partial.ajax": "true", "javax.faces.source": source,
             "javax.faces.partial.execute": process or source, "javax.faces.partial.render": update,
             source: source, form: form, "javax.faces.ViewState": self.vs}
        if event != "action":
            d["javax.faces.behavior.event"] = event
            d["javax.faces.partial.event"] = event
        if extra:
            d.update(extra)
        txt = self._req(self.path.split("?")[0], d, ajax=True)
        self._vs(txt)
        return txt


def updates(txt):
    return dict(re.findall(r'<update id="([^"]+)"><!\[CDATA\[(.*?)\]\]></update>', txt, re.S))
