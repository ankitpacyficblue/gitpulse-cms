# Showing published posts on a website

Publishing in GitPulse makes the post public at once. There is no commit, release, secret or webhook.

## Any website: one line

    <script src="https://gitpulsecms.vercel.app/api/public/projects/PROJECT_ID/embed.js" async></script>

Replace PROJECT_ID with the blog project's number. It lists the posts where the script sits (or inside an element
with the `data-gitpulse` attribute) and opens one at `#post=<slug>`. It uses the site's own styles.

Limits: posts are drawn in the browser, so they have no page of their own, title tag or sitemap entry for search
engines, and only basic Markdown (headings, lists, links, bold, images) is formatted. A site with a strict
Content-Security-Policy must allow the GitPulse address in `script-src` and `connect-src`.

## Sites that need search indexing: the public API

Fetch on the server and cache for about 60 seconds. No key is needed.

    GET /api/public/projects/PROJECT_ID/posts           list
    GET /api/public/projects/PROJECT_ID/posts/<slug>    one post (body is Markdown)

## Committing to a repository (older path)

Off by default. Set `PUBLISH_VIA_GIT=1` on the server to commit each post to the project's repository instead. It
applies to every account on that server.
