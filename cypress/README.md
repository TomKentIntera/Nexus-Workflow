# Cypress Test Scripts

This directory contains Cypress end-to-end test scripts for automating posting to various platforms.

## Test Scripts

### PostToPatreon.js
Automates posting content to Patreon. Supports:
- Automatic login
- Creating posts with title and content
- Uploading images
- Custom post content via environment variables

### PostToReddit.js
Automates posting content to Reddit with images. Supports:
- Automatic login
- Posting to r/InkByTwilight subreddit
- Image posts with title and description
- Image download from API endpoint (format: http://127.0.0.1:7860/api/images/runs/{run-id}/{timestamp}.png)
- Custom content via environment variables

## Setup

1. **Install Cypress** (if not already installed):
   ```bash
   npm install cypress --save-dev
   ```

2. **Configure Environment Variables**:
   Create a `.env` file or set environment variables:
   ```bash
   # Reddit
   REDDIT_USERNAME=your_username
   REDDIT_PASSWORD=your_password
   REDDIT_SUBREDDIT=your_subreddit
   
   # Patreon
   PATREON_EMAIL=your_email
   PATREON_PASSWORD=your_password
   
   # Post Content
   POST_TITLE=Your Post Title
   POST_DESCRIPTION=Your post description/body text
   # IMAGE_URL format: http://127.0.0.1:7860/api/images/runs/{run-id}/{timestamp}.png
   IMAGE_URL=http://127.0.0.1:7860/api/images/runs/1f7aa376-84f9-4d12-bb69-691b86ef7656/1766053697.png
   ```

## Running Tests

### Run all tests:
```bash
npx cypress run
```

### Run specific test:
```bash
npx cypress run --spec "cypress/e2e/PostToReddit.js"
```

### Run in headed mode (see browser):
```bash
npx cypress open
```

### Run with environment variables:
```bash
REDDIT_USERNAME=user REDDIT_PASSWORD=pass npx cypress run --spec "cypress/e2e/PostToReddit.js"
```

## Running from n8n

See `services/n8n/scripts/cypress/README.md` for instructions on running these tests from n8n workflows.

Example:
```bash
python /mnt/scripts/cypress/run_tests.py \
  --project /path/to/Nexus-Workflow \
  --spec cypress/e2e/PostToReddit.js \
  --headless \
  --env '{"REDDIT_USERNAME": "user", "REDDIT_PASSWORD": "pass"}' \
  --reporter json \
  --output-dir /tmp/cypress-results
```

## Notes

- These scripts interact with real websites and may need updates if the website UI changes
- Be cautious with credentials - use environment variables or secure secret management
- Reddit and Patreon may have rate limits - space out your test runs accordingly
- Some selectors may need adjustment based on the current UI of these platforms

