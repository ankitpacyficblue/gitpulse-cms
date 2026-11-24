-- ====================================================================
-- GitPulse CMS - Supabase PostgreSQL Schema Architecture
-- Multi-Tenant / Multi-Client GitHub Blog Publishing Engine
-- ====================================================================

-- 1. Clients / Organizations Table (Multi-tenant grouping)
CREATE TABLE IF NOT EXISTS public.clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    contact_email TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Projects Table (Repositories connected to GitPulse CMS)
CREATE TABLE IF NOT EXISTS public.projects (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id UUID REFERENCES public.clients(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    github_repo TEXT NOT NULL,
    github_branch TEXT NOT NULL DEFAULT 'main',
    github_token TEXT DEFAULT '',
    target_framework TEXT NOT NULL DEFAULT 'nextjs',
    content_dir TEXT NOT NULL DEFAULT 'content/posts',
    file_extension TEXT NOT NULL DEFAULT '.mdx',
    frontmatter_template TEXT NOT NULL,
    topic TEXT NOT NULL,
    target_audience TEXT NOT NULL DEFAULT 'Customers and Tech Readers',
    tone TEXT NOT NULL DEFAULT 'Authoritative, engaging, and practical',
    keywords TEXT NOT NULL DEFAULT '',
    author_name TEXT NOT NULL DEFAULT 'Editorial Team',
    publishing_mode TEXT NOT NULL DEFAULT 'pr', -- 'pr' or 'direct'
    publish_time TEXT NOT NULL DEFAULT '09:00',
    is_active BOOLEAN NOT NULL DEFAULT true,
    auto_publish BOOLEAN NOT NULL DEFAULT true,
    forbidden_words TEXT NOT NULL DEFAULT '',
    webhook_secret TEXT NOT NULL DEFAULT '',
    zero_redeploy_enabled BOOLEAN NOT NULL DEFAULT true,
    blog_page_path TEXT NOT NULL DEFAULT 'public/blog/index.html',
    last_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 3. Posts Table (Articles generated and published per repository)
CREATE TABLE IF NOT EXISTS public.posts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    content_markdown TEXT NOT NULL,
    frontmatter_yaml TEXT NOT NULL,
    target_path TEXT NOT NULL,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    meta_seo JSONB NOT NULL DEFAULT '{}'::jsonb,
    image_prompt TEXT DEFAULT '',
    og_image_svg TEXT DEFAULT '',
    seo_score INTEGER DEFAULT 100,
    seo_issues JSONB DEFAULT '[]'::jsonb,
    views INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft', -- 'draft', 'in_review', 'scheduled', 'publishing', 'published', 'failed'
    github_commit_sha TEXT,
    github_pr_url TEXT,
    github_pr_number INTEGER,
    error_message TEXT,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 4. System Logs Table (Audit trail)
CREATE TABLE IF NOT EXISTS public.system_logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT REFERENCES public.projects(id) ON DELETE CASCADE,
    post_id BIGINT REFERENCES public.posts(id) ON DELETE SET NULL,
    level TEXT NOT NULL DEFAULT 'INFO',
    message TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 5. Settings Table (Global configurations)
CREATE TABLE IF NOT EXISTS public.settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 6. Users Table (Administrators and Editors)
CREATE TABLE IF NOT EXISTS public.users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    totp_secret TEXT DEFAULT '',
    totp_enabled BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 7. Sessions Table (Active authenticated user sessions)
CREATE TABLE IF NOT EXISTS public.sessions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token TEXT UNIQUE NOT NULL,
    user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    expires_at DOUBLE PRECISION NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 8. Login Attempts Table (Brute-force protection & account lockout)
CREATE TABLE IF NOT EXISTS public.login_attempts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ip_address TEXT NOT NULL,
    username TEXT NOT NULL,
    attempt_time DOUBLE PRECISION NOT NULL,
    success INTEGER NOT NULL DEFAULT 0
);

-- 9. Post Views Analytics Table
CREATE TABLE IF NOT EXISTS public.post_views (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    post_id BIGINT NOT NULL REFERENCES public.posts(id) ON DELETE CASCADE,
    viewed_at TIMESTAMPTZ DEFAULT now(),
    ip_hash TEXT NOT NULL
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_projects_repo ON public.projects (github_repo);
CREATE INDEX IF NOT EXISTS idx_posts_project_slug ON public.posts (project_id, slug);
CREATE INDEX IF NOT EXISTS idx_posts_status ON public.posts (status);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON public.sessions (token);
CREATE INDEX IF NOT EXISTS idx_login_attempts ON public.login_attempts (ip_address, username, attempt_time);

-- Row Level Security (RLS)
ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

-- Allow public read access to published posts for the Zero-Redeploy dynamic blog page
CREATE POLICY "Public can view published posts" ON public.posts
    FOR SELECT USING (status = 'published');

CREATE POLICY "Public can view active projects" ON public.projects
    FOR SELECT USING (is_active = true);
