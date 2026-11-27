"""Every page links the favicon, and the files it links are there for local and Vercel serving."""
import re
import unittest

from tests import _env
from server.routes_web import render_dashboard_html, render_login_html


class FaviconTests(unittest.TestCase):
    def test_pages_link_icons_that_exist(self):
        for html in (render_login_html(), render_dashboard_html()):
            links = re.findall(r'<link rel="(?:icon|apple-touch-icon)" href="/(static/img/[^"]+)"', html)
            self.assertEqual(len(links), 3)
            for rel in links:
                for root in (_env.ROOT, _env.ROOT + "/public"):
                    with open(f"{root}/{rel}", "rb") as f:
                        self.assertTrue(f.read(), rel)
