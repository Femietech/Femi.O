# GitHub Actions workflow for autonomous blog posting
name: AutoBlog Twice Daily

on:
  schedule:
    - cron: '0 6,18 * * *'  # Runs at 06:00 and 18:00 UTC daily
  workflow_dispatch:

jobs:
  autoblog:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          # Add any required pip installs here

      - name: Generate blog post
        run: python generate_post.py

      - name: Find latest post
        id: find_post
        run: |
          latest_post=$(ls -t posts/*.html | head -n1)
          echo "latest_post=$latest_post" >> $GITHUB_OUTPUT

      - name: Publish to Blogspot
        run: python publish_post.py ${{ steps.find_post.outputs.latest_post }}
        env:
          GOOGLE_CLIENT_SECRET: ${{ secrets.GOOGLE_CLIENT_SECRET }}

      - name: Commit new post
        run: |
          git config --global user.name 'github-actions[bot]'
          git config --global user.email 'github-actions[bot]@users.noreply.github.com'
          git add posts/*.html
          git commit -m "Add new blog post" || echo "No changes to commit"
          git push
