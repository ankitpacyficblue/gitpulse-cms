# How a published post reaches a website

Publishing makes the post public in GitPulse at once. Nothing is committed to any repository.

The website reads the posts on its server and shows each at `<website>/blog/<slug>`:

    GET /api/public/projects/PROJECT_ID/posts           list
    GET /api/public/projects/PROJECT_ID/posts/<slug>    one post (body is Markdown)
    GET /api/public/media/<token>                       a file of a published post

Readers must never see the GitPulse address: the website serves media through its own route.

Save the website address under Settings. Post links ("View post", WhatsApp announcements) use it. Without it a post
still publishes, but has no link and is not announced.

## Search fields

| Field (writer and editor API) | Use | When empty |
|---|---|---|
| `seo_title` | page title and social title | the post title |
| `meta_description` | description | the first lines of the text |
| `keyword` | focus phrase; separate several with commas | no keywords |
| `images[].og` | the social sharing image (not shown in the article) | the cover |
| `images[].alt` | image alt text | the post title for the social image |
