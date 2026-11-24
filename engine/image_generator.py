"""
GitPulse CMS - Hero & OpenGraph Image Generator
Zero-dependency SVG card synthesis generating 1200x630 branded banner assets.
Used for Git repository asset commits and public OpenGraph previews.
"""

import base64
import html
from typing import List, Optional

def wrap_text(text: str, max_chars: int = 38) -> List[str]:
    """Wrap title into clean lines for banner rendering."""
    words = text.strip().split()
    lines = []
    current_line = []
    current_len = 0

    for word in words:
        if current_len + len(word) + 1 <= max_chars:
            current_line.append(word)
            current_len += len(word) + 1
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_len = len(word)

    if current_line:
        lines.append(" ".join(current_line))
        
    return lines[:3] # Maximum 3 lines

def generate_hero_svg(
    title: str,
    category: str = "Engineering",
    author: str = "Editorial Team",
    reading_time: int = 5,
    primary_color: str = "#6366f1",
    secondary_color: str = "#06b6d4"
) -> str:
    """
    Synthesize an eye-catching 1200x630 OpenGraph / Hero Image SVG.
    """
    safe_title_lines = [html.escape(line) for line in wrap_text(title, max_chars=34)]
    safe_category = html.escape(category.upper()[:24])
    safe_author = html.escape(author[:30])
    
    # Calculate title y positions
    start_y = 260 if len(safe_title_lines) <= 2 else 230
    title_spans = ""
    for i, line in enumerate(safe_title_lines):
        y_pos = start_y + (i * 68)
        title_spans += f'<text x="80" y="{y_pos}" fill="#f8fafc" font-size="52" font-weight="800" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif">{line}</text>\n'

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
  <defs>
    <!-- Background Gradients -->
    <linearGradient id="bg-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#020617"/>
      <stop offset="50%" stop-color="#0b1329"/>
      <stop offset="100%" stop-color="#020617"/>
    </linearGradient>
    <linearGradient id="accent-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{primary_color}"/>
      <stop offset="100%" stop-color="{secondary_color}"/>
    </linearGradient>
    <linearGradient id="glow-grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{primary_color}" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="{secondary_color}" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="corner-glow" cx="100%" cy="0%" r="60%">
      <stop offset="0%" stop-color="{secondary_color}" stop-opacity="0.18"/>
      <stop offset="100%" stop-color="#020617" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.8" stroke-opacity="0.5"/>
    </pattern>
  </defs>

  <!-- Canvas Base -->
  <rect width="1200" height="630" fill="url(#bg-grad)"/>
  <rect width="1200" height="630" fill="url(#grid)"/>
  <rect width="1200" height="630" fill="url(#corner-glow)"/>

  <!-- Left Accent Bar -->
  <rect x="0" y="0" width="10" height="630" fill="url(#accent-grad)"/>

  <!-- Top Category Pill -->
  <rect x="80" y="70" width="{max(120, len(safe_category) * 11 + 32)}" height="36" rx="18" fill="#1e293b" stroke="{primary_color}" stroke-opacity="0.4" stroke-width="1.5"/>
  <circle cx="100" cy="88" r="4" fill="{secondary_color}"/>
  <text x="114" y="94" fill="#38bdf8" font-size="13" font-weight="700" letter-spacing="1.5" font-family="-apple-system, sans-serif">{safe_category}</text>

  <!-- Title Lines -->
  {title_spans}

  <!-- Bottom Divider Line -->
  <line x1="80" y1="520" x2="1120" y2="520" stroke="#1e293b" stroke-width="1"/>

  <!-- Author & Metadata Footer -->
  <g transform="translate(80, 560)">
    <!-- Author Icon Circle -->
    <circle cx="16" cy="-4" r="16" fill="url(#accent-grad)"/>
    <text x="11" y="2" fill="#ffffff" font-size="14" font-weight="700" font-family="-apple-system, sans-serif">GP</text>

    <!-- Author & Reading Time Text -->
    <text x="44" y="-2" fill="#cbd5e1" font-size="16" font-weight="600" font-family="-apple-system, sans-serif">{safe_author}</text>
    <text x="44" y="18" fill="#64748b" font-size="13" font-family="-apple-system, sans-serif">{reading_time} min read • Verified Technical Article</text>
  </g>

  <!-- GitPulse Brand Watermark (Bottom Right) -->
  <g transform="translate(1000, 560)">
    <rect x="-10" y="-14" width="120" height="30" rx="6" fill="#0f172a" stroke="#334155" stroke-width="1"/>
    <text x="14" y="6" fill="#94a3b8" font-size="12" font-weight="700" font-family="-apple-system, sans-serif">⚡ GitPulse</text>
  </g>
</svg>"""
    return svg

def svg_to_data_uri(svg_content: str) -> str:
    """Convert SVG to base64 Data URI."""
    encoded = base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{encoded}"
