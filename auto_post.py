"""
auto_post.py
Reads config.json → generates post via Gemini → fetches images from Unsplash
→ injects images into post body → publishes to Blogger via OAuth2 refresh token.
Run by GitHub Actions twice daily.
"""

import os
import json
import datetime
import re
import requests
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# ── Load config ───────────────────────────────────────────────────────────────
with open("config.json", "r") as f:
    config = json.load(f)

TOPIC        = config.get("blog_topic", "General Knowledge")
STYLE        = config.get("blog_style", "informative and engaging")
AUDIENCE     = config.get("target_audience", "general readers")
LANGUAGE     = config.get("post_language", "English")
WORD_COUNT   = config.get("word_count", 800)
HERO_IMAGE   = config.get("hero_image", True)
INLINE_IMGS  = config.get("inline_images", 2)

# ── Env vars (set as GitHub Secrets) ─────────────────────────────────────────
GEMINI_API_KEY        = os.environ["GEMINI_API_KEY"]
BLOGGER_BLOG_ID       = os.environ["BLOGGER_BLOG_ID"]
UNSPLASH_ACCESS_KEY   = os.environ["UNSPLASH_ACCESS_KEY"]
GOOGLE_CLIENT_ID      = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET  = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_REFRESH_TOKEN  = os.environ["GOOGLE_REFRESH_TOKEN"]


# ── 1. Build Blogger credentials from OAuth2 refresh token ───────────────────
def get_blogger_service():
    """
    Uses your Client ID, Client Secret, and Refresh Token to get a fresh
    access token automatically. No service account needed.
    """
    creds = Credentials(
        token=None,                          # no access token yet — will be fetched
        refresh_token=GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/blogger"],
    )

    # Refresh to get a valid access token
    creds.refresh(Request())
    print("🔑 OAuth2 token refreshed successfully.")

    return build("blogger", "v3", credentials=creds)


# ── 2. Fetch images from Unsplash ─────────────────────────────────────────────
def fetch_unsplash_images(query, count=1):
    """
    Returns a list of image dicts. Falls back to [] on any error
    so the post still publishes without images.
    """
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={
                "query": query,
                "per_page": max(count, 3),
                "orientation": "landscape",
                "content_filter": "high",
            },
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        images = []
        for r in results[:count]:
            images.append({
                "url": r["urls"]["regular"],
                "alt": r.get("alt_description") or query,
                "photographer": r["user"]["name"],
                "profile_url": r["user"]["links"]["html"],
            })
        print(f"🖼️  Fetched {len(images)} image(s) for: '{query}'")
        return images
    except Exception as e:
        print(f"⚠️  Unsplash fetch failed ({e}), skipping images.")
        return []


def build_image_html(img, size="hero"):
    """
    Builds an HTML image block with required Unsplash attribution.
    size: 'hero' = full-width banner | 'inline' = mid-content image
    """
    attribution = (
        f'Photo by <a href="{img["profile_url"]}?utm_source=auto_blog&utm_medium=referral" '
        f'target="_blank">{img["photographer"]}</a> on '
        f'<a href="https://unsplash.com/?utm_source=auto_blog&utm_medium=referral" '
        f'target="_blank">Unsplash</a>'
    )

    if size == "hero":
        return f"""
<div style="width:100%;margin:0 0 32px 0;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.12);">
  <img src="{img['url']}"
       alt="{img['alt']}"
       style="width:100%;height:440px;object-fit:cover;display:block;" />
  <p style="font-size:11px;color:#999;margin:6px 0 0 6px;font-style:italic;">{attribution}</p>
</div>
"""
    else:
        return f"""
<div style="margin:36px auto;max-width:680px;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.10);">
  <img src="{img['url']}"
       alt="{img['alt']}"
       style="width:100%;height:300px;object-fit:cover;display:block;" />
  <p style="font-size:11px;color:#999;margin:6px 0 0 6px;font-style:italic;">{attribution}</p>
</div>
"""


# ── 3. Generate post with Gemini ──────────────────────────────────────────────
def generate_post():
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")

    today = datetime.datetime.now().strftime("%B %d, %Y")
    time_of_day = "morning" if datetime.datetime.now().hour < 14 else "evening"

    prompt = f"""
You are a professional blog writer. Write a complete, original blog post for today ({today}, {time_of_day} edition).

Topic area: {TOPIC}
Writing style: {STYLE}
Target audience: {AUDIENCE}
Language: {LANGUAGE}
Target word count: {WORD_COUNT} words

Requirements:
- Create a compelling, specific title (not generic)
- Write a full blog post with an intro, 3-5 sections with subheadings, and a conclusion
- Make it feel fresh — pick a specific angle within the topic
- End with a call-to-action or thought-provoking question for readers
- Use HTML formatting: <h2> for subheadings, <p> for paragraphs, <strong> for emphasis, <ul>/<li> for lists where relevant
- Provide a short hero_query (3-5 words) that finds a great Unsplash photo representing the post
- Provide {INLINE_IMGS} additional inline_queries for mid-article images (3-5 words each, visually distinct from each other)

Respond in this EXACT JSON format (no markdown, no code fences):
{{
  "title": "Your Post Title Here",
  "body": "<p>Full HTML content here...</p>",
  "labels": ["tag1", "tag2", "tag3"],
  "hero_query": "3 to 5 word search query",
  "inline_queries": ["query one", "query two"]
}}
"""

    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Strip markdown fences if Gemini adds them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    data = json.loads(raw)
    return (
        data["title"],
        data["body"],
        data.get("labels", [TOPIC]),
        data.get("hero_query", TOPIC),
        data.get("inline_queries", [TOPIC] * INLINE_IMGS),
    )


# ── 4. Inject images into post body ──────────────────────────────────────────
def inject_images(body, hero_img, inline_imgs):
    """
    - Hero image injected at the very top
    - Inline images inserted after every 2nd <h2> heading
    """
    result = body

    if inline_imgs:
        h2_pattern = re.compile(r"(<h2[^>]*>.*?</h2>)", re.IGNORECASE | re.DOTALL)
        parts = h2_pattern.split(result)
        rebuilt = []
        h2_count = 0
        img_index = 0

        for part in parts:
            rebuilt.append(part)
            if h2_pattern.match(part):
                h2_count += 1
                if h2_count % 2 == 0 and img_index < len(inline_imgs):
                    rebuilt.append(build_image_html(inline_imgs[img_index], size="inline"))
                    img_index += 1

        result = "".join(rebuilt)

    if hero_img:
        result = build_image_html(hero_img, size="hero") + result

    return result


# ── 5. Publish to Blogger ─────────────────────────────────────────────────────
def publish_to_blogger(service, title, body, labels):
    post = service.posts().insert(
        blogId=BLOGGER_BLOG_ID,
        body={"title": title, "content": body, "labels": labels},
        isDraft=False
    ).execute()

    print(f"✅ Published: {post['url']}")
    return post["url"]


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🔄 Topic: {TOPIC}")

    # Auth
    service = get_blogger_service()

    # Generate content
    title, body, labels, hero_query, inline_queries = generate_post()
    print(f"📝 Title: {title}")
    print(f"🔍 Queries → Hero: '{hero_query}' | Inline: {inline_queries}")

    # Fetch hero image
    hero_img = None
    if HERO_IMAGE:
        imgs = fetch_unsplash_images(hero_query, count=1)
        hero_img = imgs[0] if imgs else None

    # Fetch inline images
    inline_img_list = []
    for q in inline_queries[:INLINE_IMGS]:
        imgs = fetch_unsplash_images(q, count=1)
        if imgs:
            inline_img_list.append(imgs[0])

    # Assemble final post
    final_body = inject_images(body, hero_img, inline_img_list)

    # Publish
    url = publish_to_blogger(service, title, final_body, labels)
    print(f"🚀 Live at: {url}")
