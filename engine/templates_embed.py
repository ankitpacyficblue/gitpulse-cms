"""
GitPulse CMS - Zero-Redeploy Dynamic Blog Page Generator
Generates self-contained, SEO-optimized, client-side dynamic blog interfaces.
Commits ONCE to target repositories. When new content is published, client sites
display updates dynamically with ZERO builds, ZERO CI/CD runs, and ZERO redeployments.
"""

def generate_one_time_blog_html(project_id: int, project_name: str, cms_base_url: str = "") -> str:
    """
    Generate the zero-redeploy standalone blog page for client websites.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_name} - Official Blog</title>
    <meta name="description" content="Technical insights, engineering deep dives, and product updates from {project_name}.">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-body: #0b0f19;
            --bg-card: #111827;
            --border-card: #1f2937;
            --text-main: #f9fafb;
            --text-muted: #9ca3af;
            --accent: #6366f1;
            --accent-glow: rgba(99, 102, 241, 0.2);
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-main);
            line-height: 1.6;
        }}
        .container {{ max-width: 900px; margin: 0 auto; padding: 2rem 1rem; }}
        header {{
            border-b: 1px solid var(--border-card);
            padding: 1.5rem 0;
            margin-bottom: 2.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .brand {{ font-size: 1.35rem; font-weight: 800; color: #fff; text-decoration: none; display: flex; align-items: center; gap: 0.5rem; }}
        .badge {{ background: var(--accent-glow); color: #818cf8; font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.6rem; border-radius: 9999px; border: 1px solid rgba(99,102,241,0.3); }}
        .search-box {{ width: 100%; background: var(--bg-card); border: 1px solid var(--border-card); color: #fff; padding: 0.75rem 1rem; border-radius: 0.5rem; margin-bottom: 2rem; font-size: 0.95rem; outline: none; }}
        .search-box:focus {{ border-color: var(--accent); }}
        .post-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 0.75rem;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            transition: transform 0.2s, border-color 0.2s;
            cursor: pointer;
        }}
        .post-card:hover {{ transform: translateY(-2px); border-color: var(--accent); }}
        .post-title {{ font-size: 1.3rem; font-weight: 700; color: #fff; margin-bottom: 0.5rem; }}
        .post-excerpt {{ color: var(--text-muted); font-size: 0.95rem; margin-bottom: 1rem; }}
        .post-meta {{ display: flex; align-items: center; justify-content: space-between; font-size: 0.8rem; color: #6b7280; }}
        .tags {{ display: flex; gap: 0.4rem; }}
        .tag-pill {{ background: #1f2937; color: #cbd5e1; padding: 0.15rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; }}
        /* Detail View */
        .post-detail {{ display: none; }}
        .back-btn {{ background: transparent; border: 1px solid var(--border-card); color: var(--text-muted); padding: 0.4rem 0.8rem; border-radius: 0.375rem; cursor: pointer; margin-bottom: 1.5rem; display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; }}
        .back-btn:hover {{ color: #fff; border-color: var(--accent); }}
        .article-content {{ font-size: 1.05rem; line-height: 1.75; }}
        .article-content h1, .article-content h2, .article-content h3 {{ margin: 1.8rem 0 0.8rem; color: #fff; }}
        .article-content p {{ margin-bottom: 1.25rem; color: #d1d5db; }}
        .article-content pre {{ background: #030712; padding: 1.25rem; border-radius: 0.5rem; border: 1px solid #1f2937; overflow-x: auto; margin: 1.5rem 0; font-family: 'Fira Code', monospace; font-size: 0.9rem; }}
        .article-content code {{ font-family: 'Fira Code', monospace; color: #38bdf8; }}
        .hero-banner {{ width: 100%; border-radius: 0.75rem; margin-bottom: 2rem; border: 1px solid var(--border-card); }}
        .loading {{ text-align: center; padding: 4rem; color: var(--text-muted); }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <a href="#" onclick="showListing(); return false;" class="brand">
                <span>{project_name}</span>
                <span class="badge">Blog</span>
            </a>
            <span style="font-size: 0.8rem; color: #6b7280;">Real-Time Feed</span>
        </header>

        <!-- Feed Listing View -->
        <div id="view-listing">
            <input type="text" id="search-input" class="search-box" placeholder="Search technical articles, tutorials, and deep-dives..." oninput="filterPosts()">
            <div id="posts-container" class="loading">Fetching latest articles...</div>
        </div>

        <!-- Single Article Detail View -->
        <div id="view-detail" class="post-detail">
            <button class="back-btn" onclick="showListing()">&larr; Back to all articles</button>
            <div id="article-header"></div>
            <div id="article-body" class="article-content"></div>
        </div>
    </div>

    <script>
        // CMS Configuration
        const CMS_API = "{cms_base_url}".replace(/\\/+$/, "") || window.location.origin;
        const PROJECT_ID = {project_id};
        let allArticles = [];

        document.addEventListener('DOMContentLoaded', () => {{
            const hash = window.location.hash.replace('#', '');
            if (hash) {{
                loadSingleArticle(hash);
            }} else {{
                fetchArticles();
            }}
            window.addEventListener('popstate', handleRouting);
        }});

        function handleRouting() {{
            const hash = window.location.hash.replace('#', '');
            if (hash) {{
                loadSingleArticle(hash);
            }} else {{
                showListing();
            }}
        }}

        async function fetchArticles() {{
            try {{
                const res = await fetch(`${{CMS_API}}/api/public/projects/${{PROJECT_ID}}/posts`);
                const data = await res.json();
                allArticles = data.posts || [];
                renderArticles(allArticles);
            }} catch (err) {{
                document.getElementById('posts-container').innerHTML = '<div style="color: #ef4444;">Unable to load blog feed. Please check connectivity.</div>';
            }}
        }}

        function renderArticles(posts) {{
            const container = document.getElementById('posts-container');
            if (!posts.length) {{
                container.innerHTML = '<div style="color: #6b7280; text-align: center; padding: 2rem;">No published articles found yet.</div>';
                return;
            }}
            container.innerHTML = posts.map(p => {{
                const tags = Array.isArray(p.tags) ? p.tags : (typeof p.tags === 'string' ? JSON.parse(p.tags || '[]') : []);
                return `
                    <div class="post-card" onclick="openArticle('${{p.slug}}')">
                        <div class="post-title">${{escapeHtml(p.title)}}</div>
                        <div class="post-excerpt">${{escapeHtml(p.excerpt)}}</div>
                        <div class="post-meta">
                            <div class="tags">${{tags.map(t => `<span class="tag-pill">${{escapeHtml(t)}}</span>`).join('')}}</div>
                            <div>${{p.published_at ? p.published_at.substring(0, 10) : 'Recent'}} • ${{p.reading_time || 5}} min read</div>
                        </div>
                    </div>
                `;
            }}).join('');
        }}

        function filterPosts() {{
            const q = document.getElementById('search-input').value.toLowerCase();
            const filtered = allArticles.filter(p => 
                p.title.toLowerCase().includes(q) || 
                p.excerpt.toLowerCase().includes(q)
            );
            renderArticles(filtered);
        }}

        async function loadSingleArticle(slug) {{
            document.getElementById('view-listing').style.display = 'none';
            const detailView = document.getElementById('view-detail');
            detailView.style.display = 'block';
            document.getElementById('article-body').innerHTML = '<div class="loading">Loading article...</div>';

            try {{
                const res = await fetch(`${{CMS_API}}/api/public/projects/${{PROJECT_ID}}/posts/${{slug}}`);
                const post = await res.json();
                if (!res.ok || !post.title) throw new Error(post.error || 'Post not found');

                document.title = `${{post.title}} - {project_name} Blog`;

                // Render Header & Image
                const ogUrl = `${{CMS_API}}/api/public/projects/${{PROJECT_ID}}/posts/${{slug}}/og-image.svg`;
                document.getElementById('article-header').innerHTML = `
                    <img src="${{ogUrl}}" alt="${{escapeHtml(post.title)}}" class="hero-banner" onerror="this.style.display='none'">
                    <h1 style="font-size: 2.2rem; font-weight: 800; color: #fff; margin-bottom: 0.5rem;">${{escapeHtml(post.title)}}</h1>
                    <div style="font-size: 0.85rem; color: #9ca3af; margin-bottom: 2rem;">
                        Published ${{post.published_at ? post.published_at.substring(0, 10) : 'Recently'}} • ${{post.reading_time || 5}} min read
                    </div>
                `;

                // Render Markdown Body
                document.getElementById('article-body').innerHTML = marked.parse(post.content_markdown || '');
            }} catch (err) {{
                document.getElementById('article-body').innerHTML = `<div style="color: #ef4444;">Failed to load post: ${{err.message}}</div>`;
            }}
        }}

        function openArticle(slug) {{
            window.location.hash = slug;
        }}

        function showListing() {{
            window.location.hash = '';
            document.getElementById('view-detail').style.display = 'none';
            document.getElementById('view-listing').style.display = 'block';
            document.title = "{project_name} - Official Blog";
            if (!allArticles.length) fetchArticles();
        }}

        function escapeHtml(str) {{
            if (!str) return '';
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
        }}
    </script>
</body>
</html>"""
